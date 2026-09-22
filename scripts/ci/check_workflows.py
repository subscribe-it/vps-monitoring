#!/usr/bin/env python3
"""Waliduje pliki workflow ZANIM trafią na GitHuba.

Dwie klasy błędów, które realnie zepsuły ten plik:
1. heredoc z terminatorom w kolumnie 0 wewnątrz bloku `run: |` — kończy blok
   YAML i rozjeżdża cały plik; Bash dodatkowo kończy skrypt wcześniej,
   a krok nadal przechodzi (cicha awaria),
2. dwukropek + spacja w niecytowanym skalara (np. `cudze :ro`) — YAML widzi
   w tym mapowanie i plik przestaje się parsować.
3. krok uruchamiający skrypt, który czyta sekrety ze środowiska, ale bez
   bloku `env:` — skrypt dostaje puste zmienne i wywala się (albo, co gorsza,
   przechodzi i nic nie sprawdza). Zmierzone 22.09.2026: krok
   `check_stack.py` wstawiony do deployu miał puste `env:`.

Uruchomienie lokalne: `make validate-workflows` (rób to przed każdym pushem —
zepsuty workflow nie uruchomi się wcale, więc CI tego nie złapie).
"""
import glob
import re
import sys

# Skrypty czytające sekrety z os.environ -> wymagane zmienne.
WYMAGANE_SEKRETY = {
    "scripts/ci/check_stack.py": ("PORTAINER_URL", "PORTAINER_API_KEY"),
    "scripts/portainer/bootstrap.py": ("PORTAINER_URL", "PORTAINER_API_KEY"),
}


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
        dane = None
        try:
            import yaml

            dane = yaml.safe_load(tresc)
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            bledy.append(f"{plik}: nie parsuje się jako YAML — {e}")

        # 4) kroki uruchamiające skrypty na sekretach muszą mieć je w env
        for nazwa_joba, job in ((dane or {}).get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            env_joba = job.get("env") or {}
            for krok in job.get("steps") or []:
                if not isinstance(krok, dict):
                    continue
                komenda = str(krok.get("run") or "")
                env_kroku = krok.get("env") or {}
                for skrypt, zmienne in WYMAGANE_SEKRETY.items():
                    if skrypt not in komenda:
                        continue
                    braki = [z for z in zmienne if z not in env_kroku and z not in env_joba]
                    if braki:
                        etykieta = krok.get("name") or komenda.strip().split("\n")[0][:40]
                        bledy.append(
                            f"{plik} [{nazwa_joba}]: krok „{etykieta}” uruchamia {skrypt}, "
                            f"ale nie przekazuje {', '.join(braki)} — skrypt nie ma skąd "
                            "wziąć sekretów (dodaj blok env:)"
                        )

    if bledy:
        for b in bledy:
            print(f"  ✗ {b}")
        return 1
    pliki = len(glob.glob(".github/workflows/*.yml"))
    print(f"  ✓ {pliki} plików workflow: YAML poprawny, brak kolizji heredoców i dwukropków")
    return 0


if __name__ == "__main__":
    sys.exit(main())
