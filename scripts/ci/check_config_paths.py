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


def main() -> int:
    compose = yaml.safe_load(open("docker-compose.yml", encoding="utf-8"))
    matrix = yaml.safe_load(open(".github/workflows/build-images.yml", encoding="utf-8"))
    obrazy = {
        f"ghcr.io/subscribe-it/vps-monitoring-{i['name']}:main": i
        for i in matrix["jobs"]["build"]["strategy"]["matrix"]["include"]
    }

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

    if bledy:
        for b in bledy:
            print(f"  ✗ {b}")
        return 1
    print("  ✓ każda ścieżka config.file istnieje w obrazie")
    return 0


if __name__ == "__main__":
    sys.exit(main())
