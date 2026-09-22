#!/usr/bin/env python3
"""Ścieżka z `config.file=` w compose musi istnieć w obrazie.

Klasa błędu (realnie wystąpiła): promtail dostał `-config.file=/etc/promtail/config.yml`,
a obraz kopiował konfigurację pod inną nazwę. Proces startował bez błędu, ale
czytał DOMYŚLNY config obrazu — czyli nie zbierał niczego. Cicha awaria.
"""
import re
import sys

import yaml

WZORZEC = re.compile(r"-{1,2}config\.file=(\S+)")


def obraz_z_planisty(nazwa):
    """Dockerfile obrazu — z planisty budowy (jedno źródło prawdy o obrazach).

    Wcześniej ten skrypt parsował statyczną macierz z workflow; po przejściu na
    macierz dynamiczną (tylko zmienione obrazy) mapa mieszka w plan_builds.py.
    """
    import importlib.util
    import pathlib
    plik = pathlib.Path(__file__).with_name("plan_builds.py")
    spec = importlib.util.spec_from_file_location("plan_builds", plik)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return {f"ghcr.io/subscribe-it/vps-monitoring-{n}:main": i
            for n, i in modul.mapa_obrazow().items()}


def cele_wolumenow(usluga):
    """Ścieżki w kontenerze, pod które compose montuje wolumen."""
    cele = []
    for mont in (usluga.get("volumes") or []):
        if isinstance(mont, str) and ":" in mont:
            czesci = mont.split(":")
            if len(czesci) >= 2 and czesci[1].startswith("/"):
                cele.append(czesci[1].rstrip("/"))
        elif isinstance(mont, dict) and mont.get("target"):
            cele.append(str(mont["target"]).rstrip("/"))
    return cele


def sprzecznosc_z_wolumenem(compose, planista):
    """Plik wypalony w obrazie nie może leżeć tam, gdzie compose montuje wolumen.

    Docker kopiuje zawartość obrazu do NOWEGO wolumenu tylko przy jego pierwszym
    utworzeniu — późniejsze zmiany w obrazie są przez wolumen zasłaniane.
    Zmierzone 2026-09-22: nowy dashboard był w obrazie Grafany, ale wolumen
    `grafana_data_v2` na `/var/lib/grafana` trzymał starą kopię i Grafana
    pokazywała 4 z 5 dashboardów, bez żadnego błędu.
    """
    bledy = []
    odwrotnie = {v["dockerfile"]: n for n, v in planista.items()}
    for nazwa, usluga in compose["services"].items():
        # Planista trzyma klucze jako PEŁNE odwołania do obrazów
        # (ghcr.io/…/vps-monitoring-grafana:main), nie same nazwy.
        obraz = (usluga.get("image") or "").strip()
        dockerfile = (planista.get(obraz) or {}).get("dockerfile")
        if not dockerfile:
            continue
        tresc = open(dockerfile, encoding="utf-8").read()
        kopiowane = re.findall(r"^\s*COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)", tresc, re.I | re.M)
        for _zrodlo, cel in kopiowane:
            if not cel.startswith("/"):
                continue
            for mont in cele_wolumenow(usluga):
                if cel == mont or cel.startswith(mont + "/"):
                    bledy.append(f"{nazwa}: {dockerfile} kopiuje do {cel}, a compose montuje tam wolumen "
                                 f"({mont}) — zawartość obrazu będzie zasłonięta")
    return bledy


def main() -> int:
    compose = yaml.safe_load(open("docker-compose.yml", encoding="utf-8"))
    planista = obraz_z_planisty(None)
    obrazy = planista

    bledy = []
    for nazwa, usluga in compose["services"].items():
        obraz = usluga.get("image", "")
        cmd = usluga.get("command")
        elementy = cmd if isinstance(cmd, list) else ([cmd] if isinstance(cmd, str) else [])
        sciezki = [m.group(1) for el in elementy if isinstance(el, str) for m in WZORZEC.finditer(el)]
        if not sciezki:
            continue
        if obraz not in obrazy:
            bledy.append(f"{nazwa}: używa config.file, ale obraz {obraz} nie jest budowany z repo — nie da się sprawdzić")
            continue
        dockerfile = obrazy[obraz]["dockerfile"]
        tresc = open(dockerfile, encoding="utf-8").read()
        for sciezka in sciezki:
            if sciezka not in tresc:
                bledy.append(f"{nazwa}: czyta {sciezka}, ale {dockerfile} nie kopiuje niczego pod tę ścieżkę")

    bledy += sprzecznosc_z_wolumenem(compose, planista)

    if bledy:
        for b in bledy:
            print(f"  ✗ {b}")
        return 1
    print("  ✓ każda ścieżka config.file istnieje w obrazie")
    return 0


if __name__ == "__main__":
    sys.exit(main())
