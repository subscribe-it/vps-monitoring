#!/usr/bin/env python3
"""Sprawdza, czy KAŻDA reguła logowa faktycznie się zapala.

Do każdej reguły wstrzykuje pasującą linię logu i pyta Alertmanagera, które
alerty się pojawiły. Reguła z literówką w regexie jest poprawnym YAML-em
i przechodzi każdą statyczną walidację — a nie zadziała nigdy. To jedyny sposób,
żeby to wychwycić.

Uwaga o werdykcie: reguły z krótkim oknem (`rate(...[5m])`) gasną, gdy tylko
wstrzyknięte linie wypadną z okna — dlatego wynik jest sumą WSZYSTKICH
dotychczasowych sprawdzeń, a nie ostatniego. Reguły z `for: 5m` i oparte na
absencji (`absent_over_time`) wymagają ciągłego warunku przez kilka minut, więc
są raportowane osobno i nie decydują o wyniku (dlatego flaga `--pomin-dlugie`).

Użycie:
    LOKI_URL=http://127.0.0.1:3100 ALERTMANAGER_URL=http://127.0.0.1:9093 \
        python3 tests/integration/verify_log_rules.py [--czekaj 60] [--pomin-dlugie]

Uruchamiać wyłącznie lokalnie (albo w CI), nigdy przeciwko VPS-owi.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import yaml

LOKI = os.environ.get("LOKI_URL", "http://127.0.0.1:3100").rstrip("/")
AM = os.environ.get("ALERTMANAGER_URL", "http://127.0.0.1:9093").rstrip("/")

# (alert, strumień, treść linii) — treści są wzięte z REALNYCH formatów logów
PRZYPADKI = [
    ("PgPageVerificationFailed", {"stack": "ventiplan-prod", "service": "postgres"},
     "2026-09-21 01:13:07 UTC [123] LOG:  page verification failed, calculated checksum 1 but expected 2"),
    ("PgPanic", {"stack": "ventiplan-prod", "service": "postgres"},
     "2026-09-21 01:13:07 UTC [123] PANIC:  database system was interrupted; last known up at 2026-09-21 01:00:00 UTC"),
    ("PgStorageProblem", {"stack": "ventiplan-prod", "service": "postgres"},
     "2026-09-21 01:13:07 UTC [123] ERROR:  could not extend file: No space left on device"),
    ("PgConnectionRefused", {"stack": "ventiplan-prod", "service": "postgres"},
     "2026-09-21 01:13:07 UTC [123] FATAL:  sorry, too many clients already"),
    ("AcmeCertificateRenewalFailed", {"stack": "portainer-edge-gateway", "service": "traefik"},
     'level=error msg="Unable to obtain ACME certificate for domains \\"x.pl\\": error: acme: error: 429 rateLimited"'),
    ("TraefikRouterError", {"stack": "portainer-edge-gateway", "service": "traefik"},
     'level=error msg="error while building router: cannot find service for router x"'),
    ("SshLoginAccepted", {"job": "journald", "unit": "ssh.service"},
     "Accepted publickey for ubuntu from 195.60.64.7 port 43210 ssh2: ED25519 SHA256:abc"),
    ("SshAuthFailuresSpike", {"job": "journald", "unit": "ssh.service"},
     "Failed password for invalid user admin from 1.2.3.4 port 1234 ssh2", 51),
    ("Fail2banBanSpike", {"job": "journald", "unit": "fail2ban.service"},
     "NOTICE  [sshd] Ban 1.2.3.4", 6),
    ("CockpitLogin", {"job": "journald", "unit": "cockpit-ws"},
     "cockpit-session: Successful login for user admin from 195.60.64.7"),
    ("KernelDiskErrors", {"job": "journald", "transport": "kernel"},
     "blk_update_request: I/O error, dev sda, sector 123456 op WRITE"),
    ("KernelOomKill", {"job": "journald", "transport": "kernel"},
     "Out of memory: Killed process 1234 (node) total-vm:1000000kB"),
    ("Traefik5xxRateHigh", {"job": "traefik", "RequestHost": "app.ventiplan.pl"},
     json.dumps({"RequestHost": "app.ventiplan.pl", "DownstreamStatus": 500}), 120),
]


def reguly_wolne():
    """Alerty, których nie da się zapalić jednorazowym wstrzyknięciem.

    Kryterium czytane z plików reguł: `for` >= 5m (trzeba podtrzymać warunek)
    albo wyrażenie oparte na absencji (`absent_over_time`).
    """
    wolne = set()
    wzorzec = os.path.join(os.path.dirname(__file__), "..", "..", "config", "loki", "rules")
    for plik in glob.glob(os.path.join(wzorzec, "**", "*.yml"), recursive=True):
        with open(plik, encoding="utf-8") as f:
            dane = yaml.safe_load(f)
        for grupa in dane.get("groups", []):
            for r in grupa.get("rules", []):
                expr = r.get("expr", "")
                for_ = str(r.get("for", "0m"))
                minuty = 0
                m = re.match(r"^(\d+)m$", for_)
                if m:
                    minuty = int(m.group(1))
                if "absent_over_time" in expr or minuty >= 5:
                    wolne.add(r["alert"])
    return wolne


def wyslij(przypadki):
    teraz = time.time_ns()
    streams = []
    for wpis in przypadki:
        alert, strumien, linia = wpis[0], wpis[1], wpis[2]
        powtorzen = wpis[3] if len(wpis) > 3 else 1
        wartosci = []
        for i in range(powtorzen):
            # rozrzucamy w czasie, żeby `rate(...[5m])` miało z czego liczyć
            ts = teraz - (powtorzen - i) * 2_000_000_000
            wartosci.append([str(ts), linia])
        streams.append({"stream": dict(strumien, host="test-regul"), "values": wartosci})
    dane = json.dumps({"streams": streams}).encode()
    z = urllib.request.Request(LOKI + "/loki/api/v1/push", data=dane,
                               headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(z, timeout=20) as r:
        return r.status


def alerty():
    with urllib.request.urlopen(AM + "/api/v2/alerts", timeout=15) as r:
        return json.load(r)


def nazwy_alertow():
    return {a["labels"].get("alertname") for a in alerty()}


def zbieraj_przez(sekundy, widziane, krok=15):
    """Odpytywać Alertmanagera co `krok` s i sumować — nie raz na końcu.

    Reguła z oknem 5 min gaśnie, gdy wstrzyknięte linie wypadną z okna. Pojedyncze
    sprawdzenie po odczekaniu zgłosiłoby ją jako „nie zadziałała", choć zadziałała.
    """
    koniec = time.time() + sekundy
    while time.time() < koniec:
        time.sleep(min(krok, max(0.5, koniec - time.time())))
        widziane |= nazwy_alertow()
    return widziane


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--czekaj", type=int, default=60, help="ile sekund czekać na reguły natychmiastowe")
    p.add_argument("--czekaj-dlugie", type=int, default=360, help="ile czekać na reguły czasowe")
    p.add_argument("--pomin-dlugie", action="store_true",
                   help="nie czekaj na reguły z `for: 5m` (i tak wymagają ciągłego warunku)")
    args = p.parse_args()

    wolne = reguly_wolne()
    oczekiwane = {w[0] for w in PRZYPADKI}
    szybkie = oczekiwane - wolne

    print(f"  Loki: {LOKI} | Alertmanager: {AM}")
    print(f"  wysyłam linie dla {len(PRZYPADKI)} reguł…")
    print(f"  push → HTTP {wyslij(PRZYPADKI)}")

    czas = time.strftime("%H:%M:%S")
    print(f"  [{czas}] czekam {args.czekaj} s na reguły natychmiastowe…")
    # Suma wszystkich sprawdzeń: alert, który zapalił się i wygasł w trakcie,
    # nadal jest dowodem, że reguła działa.
    widziane = zbieraj_przez(args.czekaj, set())

    braki_szybkie = sorted(szybkie - widziane)
    if braki_szybkie and not args.pomin_dlugie:
        print(f"  [{time.strftime('%H:%M:%S')}] czekam jeszcze {args.czekaj_dlugie} s (reguły czasowe)…")
        widziane = zbieraj_przez(args.czekaj_dlugie, widziane)

    print()
    print(f"  zapalone (natychmiastowe): {len(szybkie & widziane)}/{len(szybkie)}")
    for n in sorted(szybkie & widziane):
        print(f"    ✓ {n}")
    for n in sorted(braki_szybkie):
        print(f"    ✗ {n} — NIE zapaliła się")

    if wolne:
        print()
        print("  z czasu (wymagają ciągłego warunku — nie wstrzykiwane):")
        for n in sorted(wolne):
            zjawil = "✓ zapaliła się sama" if n in widziane else "· nie sprawdzana"
            print(f"    {zjawil}: {n}")

    print()
    if braki_szybkie:
        print(f"  WYNIK: ✗ nie zadziałały: {braki_szybkie}")
        return 1
    print(f"  WYNIK: ✓ wszystkie {len(szybkie)} reguły natychmiastowe zadziałały")
    return 0


if __name__ == "__main__":
    sys.exit(main())
