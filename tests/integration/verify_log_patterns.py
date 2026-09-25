#!/usr/bin/env python3
"""Sprawdza KAŻDĄ gałąź KAŻDEGO regexu w regułach logowych Loki.

Po co: Loki 3.6.17 potrafi przyjąć poprawny regex i **nigdy nie dopasować
niczego**. Wzorzec `X.*(a|b)` (kropka-gwiazdka bezpośrednio przed grupą z
alternacją) nie łapie ANI `a`, ANI `b` — bez błędu, bez logu, bez śladu.
Reguła z takim wzorcem jest trwale martwa i wygląda na sprawną.

Dlatego każda gałąź alternacji dostaje tu własną linię logu i własny strumień
(etykieta `przypadek`), a regex jest wyciągany **z pliku reguł** — nie kopiowany.
Dzięki temu test nie może się rozjechać z tym, co trafia na produkcję.

Użycie:
    LOKI_URL=http://127.0.0.1:3100 python3 tests/integration/verify_log_patterns.py

Uruchamiać wyłącznie lokalnie (albo w CI), nigdy przeciwko VPS-owi.
"""
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import yaml

LOKI = os.environ.get("LOKI_URL", "http://127.0.0.1:3100").rstrip("/")
REGUŁY = os.path.join(os.path.dirname(__file__), "..", "..", "config", "loki", "rules")

PG = {"stack": "ventiplan-prod", "service": "postgres"}
EDGE = {"stack": "portainer-edge-gateway", "service": "traefik"}
SSH = {"job": "journald", "unit": "ssh.service"}
# Bany fail2bana są w PLIKU (job `fail2ban` w promtailu), nie w journald:
# fail2ban pisze do journala tylko start/stop (zmierzone 22.09.2026).
F2B = {"job": "fail2ban", "host": "ovh-vps-1"}
COCKPIT = {"job": "journald", "unit": "cockpit-ws"}
KERNEL = {"job": "journald", "transport": "kernel"}
TRAEFIK = {"job": "traefik"}

# (alert, opis gałęzi, strumień, linia logu). Jedna linia = jedna gałąź:
# dobrana tak, żeby pasowała WYŁĄCZNIE do sprawdzanej gałęzi.
PRZYPADKI = [
    # --- postgres: uszkodzenie stron/WAL (sygnał z 21.09.2026) ---------------
    ("PgPageVerificationFailed", "page verification failed", PG,
     "2026-09-21 01:13:07 UTC [123] LOG:  page verification failed, calculated checksum 1 but expected 2"),
    ("PgPageVerificationFailed", "invalid checkpoint", PG,
     "2026-09-21 01:13:07 UTC [123] LOG:  invalid checkpoint record at 0/1A2B3C"),
    ("PgPageVerificationFailed", "could not locate a valid checkpoint", PG,
     "2026-09-21 01:13:07 UTC [123] FATAL:  could not locate a valid checkpoint record"),
    ("PgPageVerificationFailed", "WAL … corrupt", PG,
     "2026-09-21 01:13:07 UTC [123] LOG:  WAL segment corrupt at 0/1A2B3C"),
    ("PgPageVerificationFailed", "WAL … invalid", PG,
     "2026-09-21 01:13:07 UTC [123] LOG:  WAL record invalid, retrying"),
    ("PgPageVerificationFailed", "incorrect resource manager", PG,
     "2026-09-21 01:13:07 UTC [123] FATAL:  incorrect resource manager data checksum in record"),
    # --- postgres: PANIC ----------------------------------------------------
    ("PgPanic", "PANIC:", PG,
     "2026-09-21 01:13:07 UTC [123] PANIC:  could not write to log file"),
    ("PgPanic", "database system was interrupted", PG,
     "2026-09-21 01:13:07 UTC [123] LOG:  database system was interrupted; last known up at 2026-09-21 01:00:00 UTC"),
    ("PgPanic", "server process … terminated by signal", PG,
     "2026-09-21 01:13:07 UTC [123] LOG:  server process (PID 1234) was terminated by signal 9: Killed"),
    ("PgPanic", "terminating any other active server processes", PG,
     "2026-09-21 01:13:07 UTC [123] LOG:  terminating any other active server processes"),
    # --- postgres: brak miejsca/pamięci -------------------------------------
    ("PgStorageProblem", "no space left on device", PG,
     "2026-09-21 01:13:07 UTC [123] ERROR:  could not write to file: No space left on device"),
    ("PgStorageProblem", "could not extend file", PG,
     "2026-09-21 01:13:07 UTC [123] ERROR:  could not extend file: wrote only 4096 of 8192 bytes"),
    ("PgStorageProblem", "out of memory", PG,
     "2026-09-21 01:13:07 UTC [123] ERROR:  out of memory"),
    ("PgStorageProblem", "could not resize shared memory", PG,
     "2026-09-21 01:13:07 UTC [123] ERROR:  could not resize shared memory segment to 1234 bytes"),
    ("PgStorageProblem", "disk full", PG,
     "2026-09-21 01:13:07 UTC [123] ERROR:  disk full, aborting"),
    # --- postgres: odrzucane połączenia -------------------------------------
    ("PgConnectionRefused", "too many clients", PG,
     "2026-09-21 01:13:07 UTC [123] FATAL:  sorry, too many clients already"),
    ("PgConnectionRefused", "remaining connection slots", PG,
     "2026-09-21 01:13:07 UTC [123] FATAL:  remaining connection slots are reserved for non-replication superuser connections"),
    ("PgConnectionRefused", "database system is in recovery mode", PG,
     "2026-09-21 01:13:07 UTC [123] FATAL:  the database system is in recovery mode"),
    # --- jądro: błędy dysku (zastępstwo SMART) ------------------------------
    ("KernelDiskErrors", "I/O error", KERNEL,
     "sd 0:0:0:0: [sda] I/O error, dev sda, sector 123456 op WRITE"),
    ("KernelDiskErrors", "blk_update_request", KERNEL,
     "blk_update_request: critical target error, dev sda, sector 88"),
    ("KernelDiskErrors", "EXT4-fs error", KERNEL,
     "EXT4-fs error (device sda1): ext4_find_entry:1455: inode #2: comm ls: reading directory"),
    ("KernelDiskErrors", "nvme … error", KERNEL,
     "nvme0: error processing command, aborting"),
    ("KernelDiskErrors", "nvme … I/O", KERNEL,
     "nvme0n1: resetting controller after I/O timeout"),
    ("KernelDiskErrors", "medium error", KERNEL,
     "ata1.00: medium error, dev sda, sector 4096"),
    ("KernelDiskErrors", "Buffer I/O error", KERNEL,
     "Buffer I/O error on dev sda1, logical block 12345, lost async page write"),
    ("KernelDiskErrors", "ataN.MM:", KERNEL,
     "ata1.00: configured for UDMA/133"),
    ("KernelDiskErrors", "failed command", KERNEL,
     "failed command: WRITE FPDMA QUEUED"),
    ("KernelOomKill", "Out of memory: Killed process", KERNEL,
     "Out of memory: Killed process 1234 (node) total-vm:1000000kB, anon-rss:500000kB"),
    # --- bezpieczeństwo -----------------------------------------------------
    ("SshLoginAccepted", "Accepted publickey for", SSH,
     "Accepted publickey for ubuntu from 195.60.64.7 port 43210 ssh2: ED25519 SHA256:abc"),
    ("SshLoginAccepted", "Accepted password for", SSH,
     "Accepted password for root from 195.60.64.7 port 43211 ssh2"),
    ("SshAuthFailuresSpike", "Failed password", SSH,
     "Failed password for invalid user admin from 1.2.3.4 port 1234 ssh2"),
    ("SshAuthFailuresSpike", "Invalid user", SSH,
     "Invalid user oracle from 1.2.3.4 port 1235"),
    ("SshAuthFailuresSpike", "Connection closed by authenticating user", SSH,
     "Connection closed by authenticating user root 1.2.3.4 port 1236 [preauth]"),
    ("Fail2banBanSpike", "Ban ", F2B,
     "2026-09-21 01:13:07,123 fail2ban.actions NOTICE [sshd] Ban 1.2.3.4"),
    ("CockpitLogin", "successful login", COCKPIT,
     "cockpit-session: Successful login for user admin from 195.60.64.7"),
    ("CockpitLogin", "logged in", COCKPIT,
     "cockpit-ws: user admin logged in from 195.60.64.7"),
    ("CockpitLogin", "login for user", COCKPIT,
     "cockpit-session: login for user admin"),
    ("CockpitLogin", "session opened", COCKPIT,
     "systemd-logind: session opened for user admin"),
    ("CockpitLogin", "session started", COCKPIT,
     "cockpit-session: session started for admin"),
    ("CockpitLogin", "new session", COCKPIT,
     "cockpit-ws: new session 42 established"),
    ("CockpitLogin", "authentication", COCKPIT,
     "cockpit-ws: authentication succeeded for admin"),
    # --- edge / certyfikaty -------------------------------------------------
    ("AcmeCertificateRenewalFailed", "unable to obtain ACME certificate", EDGE,
     'level=error msg="Unable to obtain ACME certificate for domains \\"x.pl\\""'),
    ("AcmeCertificateRenewalFailed", "error … acme", EDGE,
     'level=error msg="error: acme: error: 429 :: rateLimited, retrying"'),
    ("AcmeCertificateRenewalFailed", "acme … error", EDGE,
     'level=error msg="acme: error present, aborting"'),
    ("AcmeCertificateRenewalFailed", "cannot obtain certificate", EDGE,
     'level=error msg="cannot obtain certificate for domain y.pl"'),
    ("AcmeCertificateRenewalFailed", "rateLimited", EDGE,
     'level=error msg="rateLimited by CA, next attempt in 24h"'),
    ("TraefikRouterError", "error while building", EDGE,
     'level=error msg="error while building router: cannot find service"'),
    ("TraefikRouterError", "cannot find service", EDGE,
     'level=error msg="cannot find service for router x"'),
    ("TraefikRouterError", "no available server", EDGE,
     'level=error msg="no available server, load balancer is empty"'),
    ("TraefikRouterError", "error … middleware", EDGE,
     'level=error msg="error while adding middleware: bad config"'),
]

# Reguły bez filtra tekstowego (JSON/PromQL-owe) — inny kształt, więc osobno.
BEZ_REGEXU = [
    ("Traefik5xxRateHigh", "DownstreamStatus >= 500", TRAEFIK,
     json.dumps({"RequestHost": "app.ventiplan.pl", "DownstreamStatus": 500}),
     "| json | DownstreamStatus >= 500"),
    ("Traefik5xxCountHigh", "DownstreamStatus >= 500", TRAEFIK,
     json.dumps({"RequestHost": "app.ventiplan.pl", "DownstreamStatus": 503}),
     "| json | DownstreamStatus >= 500"),
]


def wczytaj_reguly():
    """{alert: (selektor, regex_logql)} wprost z plików reguł."""
    reguly = {}
    for plik in glob.glob(os.path.join(REGUŁY, "**", "*.yml"), recursive=True):
        with open(plik, encoding="utf-8") as f:
            dane = yaml.safe_load(f)
        for grupa in dane.get("groups", []):
            for r in grupa.get("rules", []):
                expr = r.get("expr", "")
                m = re.search(r'\|~\s*"((?:[^"\\]|\\.)*)"', expr)
                if m:
                    reguly[r["alert"]] = m.group(1)
    return reguly


def wyslij(do_wyslania):
    teraz = time.time_ns()
    streams = []
    for i, (strumien, linia) in enumerate(do_wyslania):
        streams.append({
            "stream": dict(strumien, przypadek=f"p{i}"),
            "values": [[str(teraz - i), linia]],
        })
    req = urllib.request.Request(
        LOKI + "/loki/api/v1/push",
        data=json.dumps({"streams": streams}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def czy_lapie(selektor, przypadek, filtr, okno="[10m]", potok=None):
    matchers = ", ".join(f'{k}="{v}"' for k, v in sorted(selektor.items()))
    czesc = potok if potok is not None else f"|~ {json.dumps(filtr)}"
    q = f'count_over_time({{{matchers}, przypadek="{przypadek}"}} {czesc} {okno})'
    url = LOKI + "/loki/api/v1/query?" + urllib.parse.urlencode({"query": q})
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return False, e.read().decode()[:120]
    wynik = d.get("data", {}).get("result", [])
    return bool(wynik and float(wynik[0]["value"][1]) > 0), ""


def main() -> int:
    reguly = wczytaj_reguly()
    wszystkie = [(a, opis, s, l, None) for a, opis, s, l in PRZYPADKI]
    wszystkie += [(a, opis, s, l, p) for a, opis, s, l, p in BEZ_REGEXU]

    brakujace_reguly = sorted({a for a, *_ in wszystkie} - set(reguly) - {a for a, *_ in BEZ_REGEXU})
    if brakujace_reguly:
        print(f"  ✗ reguły nie znalezione w plikach: {brakujace_reguly}")
        return 1

    print(f"  Loki: {LOKI}")
    print(f"  regexów wczytanych z plików reguł: {len(reguly)}")
    print(f"  przypadków (gałęzi) do sprawdzenia: {len(wszystkie)}")
    print(f"  push → HTTP {wyslij([(s, l) for _, _, s, l, _ in wszystkie])}")
    time.sleep(4)

    zle = []
    for i, (alert, opis, strumien, _linia, potok) in enumerate(wszystkie):
        filtr = reguly.get(alert, "")
        okno = "[5m]" if potok else "[10m]"
        ok, blad = czy_lapie(strumien, f"p{i}", filtr, okno, potok)
        if not ok:
            # Świeżo wypchnięte strumienie potrzebują chwili, żeby być widoczne
            # dla queriera — bez ponowienia test mrugałby fałszywie.
            time.sleep(5)
            ok, blad = czy_lapie(strumien, f"p{i}", filtr, okno, potok)
        if not ok:
            zle.append((alert, opis, blad))

    print()
    for alert in sorted({a for a, *_ in wszystkie}):
        ile = sum(1 for a, *_ in wszystkie if a == alert)
        zle_tej = [x for x in zle if x[0] == alert]
        status = "✓" if not zle_tej else "✗"
        print(f"  {status} {alert:32s} gałęzi: {ile - len(zle_tej)}/{ile}")
        for _, opis, blad in zle_tej:
            dodatek = f"  ({blad})" if blad else ""
            print(f"      ✗ MARTWA GAŁĄŹ: {opis}{dodatek}")

    print()
    if zle:
        print(f"  WYNIK: ✗ {len(zle)} martwych gałęzi z {len(wszystkie)}")
        print("  Uwaga: `X.*(a|b)` w Loki 3.x nie dopasowuje NICZEGO.")
        print("  Zamiast `.*(` użyj `.{0,80}(` — patrz docs/VERIFICATION.md.")
        return 1
    print(f"  WYNIK: ✓ wszystkie {len(wszystkie)} gałęzi reaguje na swoją linię")
    return 0


if __name__ == "__main__":
    sys.exit(main())
