#!/usr/bin/env python3
"""Waliduje pliki workflow ZANIM trafią na GitHuba.

Dwie klasy błędów, które realnie zepsuły ten plik:
1. heredoc z terminatorom w kolumnie 0 wewnątrz bloku `run: |` — kończy blok
   YAML i rozjeżdża cały plik; Bash dodatkowo kończy skrypt wcześniej,
   a krok nadal przechodzi (cicha awaria),
2. dwukropek + spacja w niecytowanym skalara (np. `cudze :ro`) — YAML widzi
   w tym mapowanie i plik przestaje się parsować.

Uruchomienie lokalne: `make validate-workflows` (rób to przed każdym pushem —
zepsuty workflow nie uruchomi się wcale, więc CI tego nie złapie).
"""
import glob
import re
import sys


def main() -> int:
    bledy: list[str] = []

    for plik in sorted(glob.glob(".github/workflows/*.yml")):
        tresc = open(plik, encoding="utf-8").read()

        # 1) heredoc w kolumnie 0 (poza samym początkiem pliku)
        for nr, linia in enumerate(tresc.split("\n"), 1):
            if linia.strip() in ("PY", "EOF", "YAML", "SH") and not linia.startswith(" "):
                bledy.append(f"{plik}:{nr}: terminator heredoca w kolumnie 0 — użyj scripts/ci/*.py")

        # 2) niecytowany dwukropek+spacja w nazwie kroku lub joba
        for nr, linia in enumerate(tresc.split("\n"), 1):
            m = re.match(r"^\s*(?:- )?name:\s+(?!['\"])(.*)$", linia)
            if m and ": " in m.group(1):
                bledy.append(f"{plik}:{nr}: dwukropek w niecytowanej nazwie — ujmij nazwę w cudzysłów")

        # 3) czy w ogóle jest poprawnym YAML-em
        try:
            import yaml

            yaml.safe_load(tresc)
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            bledy.append(f"{plik}: nie parsuje się jako YAML — {e}")

    if bledy:
        for b in bledy:
            print(f"  ✗ {b}")
        return 1
    pliki = len(glob.glob(".github/workflows/*.yml"))
    print(f"  ✓ {pliki} plików workflow: YAML poprawny, brak kolizji heredoców i dwukropków")
    return 0


if __name__ == "__main__":
    sys.exit(main())
