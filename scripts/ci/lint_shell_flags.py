#!/usr/bin/env python3
"""Lint komend usług: flagi boolowskie w postaci `--flaga=false`.

Prometheus (kingpin) odrzuca takie flagi i wpada w pętlę restartów
("Error parsing command line arguments: unexpected false"). Ten błąd
przeszedł przez walidację statyczną i został znaleziony dopiero przez
uruchomienie stacku lokalnie — dlatego pilnuje go automat.
"""
import re
import sys

import yaml

WZORZEC = re.compile(r"--[\w.\-]+=false\b")


def main() -> int:
    compose = yaml.safe_load(open("docker-compose.yml", encoding="utf-8"))
    zle: list[str] = []
    for nazwa, usluga in compose["services"].items():
        cmd = usluga.get("command")
        elementy = cmd if isinstance(cmd, list) else ([cmd] if isinstance(cmd, str) else [])
        for el in elementy:
            if isinstance(el, str):
                for dopasowanie in WZORZEC.finditer(el):
                    zle.append(f"{nazwa}: {dopasowanie.group(0)}")
    if zle:
        print("  ✗ flagi boolowskie z =false (użyj samej flagi albo --no-…):")
        for z in zle:
            print("     ", z)
        return 1
    print("  ✓ brak flag boolowskich z =false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
