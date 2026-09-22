#!/usr/bin/env python3
"""Sprawdza, że każdy własny obraz z compose ma odpowiednik w planiście buildów.

Macierz buildów jest teraz dynamiczna (budujemy tylko zmienione obrazy), więc
listę obrazów bierzemy z planisty — jedno źródło prawdy o tym, co da się zbudować.
"""
import importlib.util
import pathlib
import sys

import yaml


def zbudowane_obrazy():
    plik = pathlib.Path(__file__).with_name("plan_builds.py")
    spec = importlib.util.spec_from_file_location("plan_builds", plik)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return {f"ghcr.io/subscribe-it/vps-monitoring-{n}:main" for n in modul.mapa_obrazow()}


def main() -> int:
    rendered = yaml.safe_load(open("/tmp/rendered.yml", encoding="utf-8"))
    zbudowane = zbudowane_obrazy()
    uzyte = {s["image"] for s in rendered["services"].values() if s.get("image")}
    wlasne = {i for i in uzyte if i.startswith("ghcr.io/subscribe-it/vps-monitoring-")}

    braki = sorted(wlasne - zbudowane)
    zbedne = sorted(zbudowane - wlasne)
    if braki:
        print("  ✗ obrazy bez jobu budującego:", braki)
    if zbedne:
        print("  ✗ macierz buduje obrazy, których nikt nie używa:", zbedne)
    if braki or zbedne:
        return 1
    print(f"  ✓ {len(wlasne)} własnych obrazów, każdy z jobem budującym")
    return 0


if __name__ == "__main__":
    sys.exit(main())
