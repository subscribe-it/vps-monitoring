#!/usr/bin/env python3
"""Sprawdza, że każdy własny obraz z compose ma job w macierzy buildów (i odwrotnie)."""
import sys

import yaml


def main() -> int:
    rendered = yaml.safe_load(open("/tmp/rendered.yml", encoding="utf-8"))
    workflow = yaml.safe_load(open(".github/workflows/build-images.yml", encoding="utf-8"))
    zbudowane = {
        f"ghcr.io/subscribe-it/vps-monitoring-{i['name']}:main"
        for i in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]
    }
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
