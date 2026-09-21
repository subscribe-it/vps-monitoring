#!/usr/bin/env python3
"""Waliduje provisioning Grafany i dashboardy (JSON + spójność uid datasource'ów)."""
import glob
import json
import sys

import yaml


def main() -> int:
    bledy: list[str] = []
    dashboardy = {}
    for plik in glob.glob("config/grafana/dashboards/*.json"):
        try:
            d = json.load(open(plik, encoding="utf-8"))
            if "uid" not in d or "panels" not in d:
                bledy.append(f"{plik}: brak uid lub panels")
            else:
                dashboardy[d["uid"]] = len(d["panels"])
        except Exception as e:  # noqa: BLE001
            bledy.append(f"{plik}: {e}")

    for plik in glob.glob("config/grafana/provisioning/**/*.yml", recursive=True):
        try:
            yaml.safe_load(open(plik, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            bledy.append(f"{plik}: {e}")

    ds = yaml.safe_load(open("config/grafana/provisioning/datasources/datasources.yml", encoding="utf-8"))
    uids = {x.get("uid") for x in ds["datasources"]}
    uzywane = set()
    for plik in glob.glob("config/grafana/dashboards/*.json"):
        tresc = open(plik, encoding="utf-8").read()
        for uid in uids:
            if f'"uid": "{uid}"' in tresc:
                uzywane.add(uid)
    brakujace = uzywane - uids
    if brakujace:
        bledy.append(f"dashboardy odwołują się do nieistniejących uid: {brakujace}")

    if bledy:
        for b in bledy:
            print(f"  ✗ {b}")
        return 1
    print(f"  ✓ {len(dashboardy)} dashboardów ({sum(dashboardy.values())} paneli), uid spójne")
    return 0


if __name__ == "__main__":
    sys.exit(main())
