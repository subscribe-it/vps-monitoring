#!/usr/bin/env python3
"""Każdy plik konfiguracyjny z config/ musi być kopiowany przez jakiś Dockerfile.

Bez tej kontroli plik potrafi leżeć w repo i NIE być używany przez nic —
dokładnie tak było z config/blackbox/blackbox.yml: kontener blackboxa korzystał
z domyślnej konfiguracji obrazu, a Prometheus odwoływał się do modułów, których
nie było (400 Unknown module → fałszywe alerty o łańcuchu monitoringu).
"""
import glob
import os
import re
import sys

# kontekst budowania per Dockerfile (jak w macierzy build-images.yml)
KONTEKSTY = {
    "dockerfiles/prometheus/Dockerfile": ".",
    "dockerfiles/alertmanager/Dockerfile": ".",
    "dockerfiles/loki/Dockerfile": ".",
    "dockerfiles/promtail/Dockerfile": ".",
    "dockerfiles/grafana/Dockerfile": ".",
    "dockerfiles/auth/Dockerfile": ".",
    "dockerfiles/blackbox/Dockerfile": ".",
    "services/discovery/Dockerfile": "services/discovery",
    "services/notifier/Dockerfile": "services/notifier",
    "services/health-ping/Dockerfile": "services/health-ping",
    "panel/Dockerfile": "panel",
}

WZORZEC_COPY = re.compile(r"^\s*COPY\s+(?:--from=\S+\s+)?(.+?)\s+\S+\s*$", re.MULTILINE)

# Świadome wyjątki: te pliki są używane przez CI (promtool test rules),
# a nie przez obrazy — nie mają prawa być nigdzie kopiowane.
WYJATKI = ("config/prometheus/tests/",)


def zebrane_sciezki() -> set[str]:
    zebrane: set[str] = set()
    for dockerfile, kontekst in KONTEKSTY.items():
        if not os.path.exists(dockerfile):
            continue
        for dopasowanie in WZORZEC_COPY.finditer(open(dockerfile, encoding="utf-8").read()):
            for zrodlo in dopasowanie.group(1).split():
                if zrodlo.startswith("--"):
                    continue
                zebrane.add(os.path.normpath(os.path.join(kontekst, zrodlo)))
    return zebrane


def main() -> int:
    zebrane = zebrane_sciezki()
    nieuzywane = []
    for plik in sorted(glob.glob("config/**/*", recursive=True)):
        if os.path.isdir(plik):
            continue
        if plik.startswith(WYJATKI):
            continue
        if not any(plik == z or plik.startswith(z.rstrip("/") + "/") for z in zebrane):
            nieuzywane.append(plik)
    if nieuzywane:
        print("  ✗ pliki konfiguracyjne, których NIE kopiuje żaden Dockerfile (martwy config):")
        for p in nieuzywane:
            print("     ", p)
        return 1
    print(f"  ✓ wszystkie pliki config/ są używane przez obrazy ({len(zebrane)} ścieżek COPY)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
