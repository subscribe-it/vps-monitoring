#!/usr/bin/env python3
"""Sprawdza zasady stacku: zero publikowanych portów, zero configów Swarma,
cudze montowania tylko :ro, limity na każdej usłudze."""
import sys

import yaml

CUDZE_ZAPISYWALNE = {"/var/run/docker.sock"}


def main() -> int:
    uslugi = yaml.safe_load(open("/tmp/rendered.yml", encoding="utf-8"))
    comp = uslugi["services"]
    bledy: list[str] = []

    opublikowane = [(n, s["ports"]) for n, s in comp.items() if s.get("ports")]
    if opublikowane:
        bledy.append(f"publikowane porty w: {opublikowane}")

    if uslugi.get("configs"):
        bledy.append("użyto Docker Swarm configs (mają być w obrazach)")

    for nazwa, s in comp.items():
        for wol in s.get("volumes") or []:
            if isinstance(wol, dict) and wol.get("type") == "bind":
                if wol.get("source") in CUDZE_ZAPISYWALNE and not wol.get("read_only"):
                    bledy.append(f"{nazwa}: {wol['source']} zamontowany bez :ro")
        if nazwa not in ("auth", "panel"):
            if not (s.get("deploy") or {}).get("resources", {}).get("limits"):
                bledy.append(f"{nazwa}: brak limitów zasobów")

    if bledy:
        for b in bledy:
            print(f"  ✗ {b}")
        return 1
    print("  ✓ wszystkie zasady stacku spełnione")
    return 0


if __name__ == "__main__":
    sys.exit(main())
