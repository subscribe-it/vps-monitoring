#!/usr/bin/env python3
"""Uruchamia polecenie w kontenerze przez API Portainera (bez SSH).

Po co: dostęp SSH do VPS-a bywa zablokowany (PerSourcePenalties OpenSSH 9.9
blokuje IP po nieudanych próbach), a Cockpit ma osobną awarię sesji. Portainer
API działa zawsze i pozwala wejść do kontenerów NASZEGO stacku, żeby np.
zapytać Loki albo sprawdzić, czy plik konfiguracyjny naprawdę jest w obrazie.

Bezpieczeństwo: domyślnie tylko kontenery ze stacku `monitoring`. Wejście do
czegokolwiek innego wymaga `--poza-stackiem` (świadoma decyzja: pozostałe
stacki są produkcyjne i nie wolno ich dotykać).

Przykłady:
    python3 scripts/portainer/exec.py monitoring_discovery -- python3 -c "import urllib.request"
    python3 scripts/portainer/exec.py monitoring_grafana -- ls /etc/grafana/dashboards
"""
import argparse
import json
import os
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request


def ustawienia():
    adres = os.environ.get("PORTAINER_URL", "").strip().rstrip("/")
    klucz = os.environ.get("PORTAINER_API_KEY", "").strip()
    if not adres:
        plik = os.path.expanduser("~/.config/portainer-monitoring.url")
        if os.path.exists(plik):
            adres = open(plik, encoding="utf-8").read().strip().rstrip("/")
    if not klucz:
        plik = os.path.expanduser("~/.config/portainer-monitoring.key")
        if os.path.exists(plik):
            klucz = open(plik, encoding="utf-8").read().strip()
    if not adres or not klucz:
        sys.exit("✗ brak PORTAINER_URL / PORTAINER_API_KEY (env albo ~/.config/portainer-monitoring.*)")
    return adres, klucz


ADRES, KLUCZ = ustawienia()


def zapytanie(metoda, sciezka, cialo=None, binarnie=False):
    dane = json.dumps(cialo).encode() if cialo is not None else None
    naglowki = {"X-API-Key": KLUCZ}
    if dane:
        naglowki["Content-Type"] = "application/json"
    req = urllib.request.Request(ADRES + sciezka, data=dane, headers=naglowki, method=metoda)
    try:
        with urllib.request.urlopen(req, timeout=120) as odp:
            tresc = odp.read()
    except urllib.error.HTTPError as blad:
        sys.exit(f"✗ {metoda} {sciezka} -> HTTP {blad.code}: {blad.read()[:300]!r}")
    if binarnie:
        return tresc
    if not tresc:
        return None
    try:
        return json.loads(tresc)
    except json.JSONDecodeError:
        return tresc


def rozkoduj(strumien):
    """Docker multiplexuje stdout/stderr 8-bajtowymi nagłówkami ramek."""
    wynik, i = [], 0
    while i + 8 <= len(strumien):
        strumien_id, dlugosc = struct.unpack(">BxxxI", strumien[i:i + 8])
        ramka = strumien[i + 8:i + 8 + dlugosc]
        i += 8 + dlugosc
        if ramka:
            wynik.append((strumien_id, ramka.decode("utf-8", "replace")))
    if not wynik:  # brak nagłówków = zwykły tekst
        return strumien.decode("utf-8", "replace")
    return "".join(tekst for _, tekst in wynik)


def kontener(nazwa, poza_stackiem):
    """Znajduje kontener po nazwie albo po nazwie usługi Swarm.

    W Swarmie kontener to `monitoring_discovery.1.<hash>`, więc dopasowujemy
    też prefiks — inaczej trzeba by znać hash zadania.
    """
    if not poza_stackiem and not nazwa.startswith("monitoring_"):
        sys.exit(f"✗ {nazwa} nie należy do stacku monitoring — dodaj --poza-stackiem, jeśli to świadome")
    kontenery = zapytanie("GET", "/api/endpoints/1/docker/containers/json?all=1") or []
    dokladne, prefiks = None, None
    for pozycja in kontenery:
        for krotka in pozycja.get("Names") or []:
            nazwa_kontenera = krotka.lstrip("/")
            if nazwa_kontenera == nazwa:
                dokladne = pozycja
            elif nazwa_kontenera.startswith(nazwa + "."):
                prefiks = prefiks or pozycja
    wybrany = dokladne or prefiks
    if not wybrany:
        sys.exit(f"✗ nie znalazłem kontenera {nazwa}")
    return wybrany["Id"], wybrany.get("State")


def main() -> int:
    parser = argparse.ArgumentParser(description="exec w kontenerze przez Portainer API")
    parser.add_argument("kontener", help="nazwa kontenera, np. monitoring_discovery")
    parser.add_argument("--poza-stackiem", action="store_true", help="zezwól na kontener spoza stacku monitoring")
    parser.add_argument("polecenie", nargs=argparse.REMAINDER, help="po `--` polecenie do uruchomienia")
    argumenty = parser.parse_args()
    polecenie = argumenty.polecenie
    if polecenie and polecenie[0] == "--":
        polecenie = polecenie[1:]
    if not polecenie:
        sys.exit("✗ podaj polecenie po `--`, np. -- ls -la /")

    identyfikator, stan = kontener(argumenty.kontener, argumenty.poza_stackiem)
    if stan != "running":
        sys.exit(f"✗ kontener {argumenty.kontener} nie działa (stan: {stan})")
    utworzone = zapytanie(
        "POST", f"/api/endpoints/1/docker/containers/{identyfikator}/exec",
        {"AttachStdout": True, "AttachStderr": True, "Tty": False, "Cmd": polecenie},
    )
    if not utworzone or "Id" not in utworzone:
        sys.exit(f"✗ nie udało się utworzyć exec: {utworzone}")
    strumien = zapytanie("POST", f"/api/endpoints/1/docker/exec/{utworzone['Id']}/start",
                         {"Detach": False, "Tty": False}, binarnie=True)
    if isinstance(strumien, bytes):
        sys.stdout.write(rozkoduj(strumien))
    inspekcja = zapytanie("GET", f"/api/endpoints/1/docker/exec/{utworzone['Id']}/json") or {}
    return int(inspekcja.get("ExitCode") or 0)


if __name__ == "__main__":
    sys.exit(main())
