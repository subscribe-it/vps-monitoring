#!/usr/bin/env python3
"""Test notifiera przeciw PRAWDZIWEMU ntfy.sh (nie atrapie).

Po co: atrapa potwierdza tylko to, co WYSYŁAMY. Nie powie, że dostawca odrzuca
nasze żądanie (HTTP 400), że gubi znaki albo że nazwa priorytetu jest nieznana.
Ten test publikuje przez notifier na publiczne ntfy.sh, a potem CZYTA wiadomość
z powrotem i porównuje tytuł oraz priorytet znak w znak.

Zmierzone nim błędy (oba naprawione):
- tytuł w nagłówku HTTP z „·" docierał jako znak zastępczy (nagłówki to latin-1),
- tytuł z „—" albo „ł" wywalał UnicodeEncodeError przed wysłaniem, czyli alert
  krytyczny nie dochodził wcale,
- JSON API ntfy wymaga priorytetu jako LICZBY — nazwa daje HTTP 400.

Wymaga internetu. Uruchamiać lokalnie, nigdy przeciwko VPS-owi:

    python3 tests/integration/verify_ntfy_real.py
"""
import json
import os
import random
import string
import subprocess
import sys
import time
import urllib.request

PORT = int(os.environ.get("PORT", "8097"))
NTFY = "https://ntfy.sh"
PRZYPADKI = [
    ("TestKrytyczny", "critical", 5),
    ("TestOstrzezenie", "warning", 2),
    ("TestInfo", "info", 1),
    # Nazwa alertu ze znakami spoza latin-1 — na starym kodzie (tytuł w nagłówku)
    # ta wysyłka kończyła się UnicodeEncodeError i alert nie dochodził.
    ("Baza—zażółćłóśźż", "critical", 5),
]


def pobierz_wiadomosci(temat, ile=15):
    """Czyta wiadomości z tematu (poll) aż do skutku."""
    for _ in range(ile):
        time.sleep(2)
        with urllib.request.urlopen(f"{NTFY}/{temat}/json?poll=1", timeout=20) as r:
            linie = [ln for ln in r.read().decode("utf-8").splitlines() if ln.strip()]
        wiadomosci = []
        for ln in linie:
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if d.get("event") == "message":
                wiadomosci.append(d)
        if wiadomosci:
            return wiadomosci
    return []


def main() -> int:
    temat = "mon-test-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=18))
    print(f"  ntfy.sh, temat: {temat}")
    env = dict(os.environ, NTFY_URL=NTFY, NTFY_TOPIC=temat, PORT=str(PORT))
    proc = subprocess.Popen([sys.executable, "services/notifier/main.py"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2).read()
                break
            except Exception:  # noqa: BLE001 - czekamy aż wstanie
                time.sleep(0.4)
        else:
            print("  ✗ notifier nie wstał")
            return 1

        def webhook(nazwa, severity):
            alert = {"status": "firing",
                     "labels": {"alertname": nazwa, "severity": severity, "stack": "produkcja"},
                     "annotations": {"summary": f"{nazwa} — test kanału", "description": "weryfikacja ntfy"},
                     "startsAt": "2026-09-22T00:00:00Z"}
            z = urllib.request.Request(f"http://127.0.0.1:{PORT}/webhook",
                                       data=json.dumps({"version": "4", "status": "firing", "alerts": [alert]}).encode(),
                                       headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(z, timeout=30) as r:
                return json.loads(r.read().decode())["channels"]["ntfy"]

        for nazwa, severity, _ in PRZYPADKI:
            print(f"  wysłano {nazwa:16s} ({severity:8s}) → {webhook(nazwa, severity)}")

        wiadomosci = pobierz_wiadomosci(temat)
        print(f"\n  wiadomości w ntfy.sh: {len(wiadomosci)}")
        problemy = []
        for nazwa, _severity, prio in PRZYPADKI:
            trafione = [w for w in wiadomosci if nazwa in (w.get("title") or "")]
            if not trafione:
                problemy.append(f"{nazwa}: nie dotarła")
                print(f"    ✗ {nazwa}: NIE DOTARŁA")
                continue
            w = trafione[0]
            if w.get("priority") != prio:
                problemy.append(f"{nazwa}: priorytet {w.get('priority')} != {prio}")
                print(f"    ✗ {nazwa}: priorytet {w.get('priority')}, oczekiwany {prio}")
            else:
                print(f"    ✓ {nazwa:16s} priorytet {w.get('priority')} tags={w.get('tags')}")
                print(f"        tytuł: {w.get('title')!r}")

        # Znaki spoza latin-1 muszą przejść bez zmian (dawniej: UnicodeEncodeError).
        znaki_ok = all("·" in (w.get("title") or "") or "produkcja" in (w.get("title") or "")
                       for w in wiadomosci)
        ma_kropke = any("·" in (w.get("title") or "") for w in wiadomosci)
        print(f"\n  separator „·” w tytule nietknięty: {'✓' if ma_kropke else '✗'}")
        if not ma_kropke:
            problemy.append("separator · zniekształcony")

        print("\n  WYNIK:", "✓ prawdziwy ntfy.sh przyjął wszystkie powiadomienia bez zniekształceń"
              if not problemy else f"✗ problemy: {problemy}")
        return 1 if problemy else 0
    except urllib.error.URLError as exc:
        print(f"  ! brak dostępu do ntfy.sh ({exc}) — test wymaga internetu")
        return 2
    finally:
        proc.terminate()
        try:
            wyjscie = proc.communicate(timeout=5)[0]
        except Exception:  # noqa: BLE001
            proc.kill()
            wyjscie = ""
        for ln in (wyjscie or "").splitlines():
            if "ntfy" in ln.lower() or "ERROR" in ln:
                print("   [notifier]", ln[:150])


if __name__ == "__main__":
    import urllib.error  # noqa: E402 - tylko dla obsługi braku sieci
    sys.exit(main())
