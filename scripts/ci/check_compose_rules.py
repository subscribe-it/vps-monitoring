#!/usr/bin/env python3
"""Sprawdza zasady stacku: zero publikowanych portów, zero configów Swarma,
cudze montowania tylko :ro, limity na każdej usłudze."""
import sys

import yaml

CUDZE_ZAPISYWALNE = {"/var/run/docker.sock"}


def etykiety(blok):
    """Labelki w obu kształtach: lista "klucz=wartość" (compose) albo mapa (po
    `docker stack config`). Bez tego kontrola porównywała jabłka z gruszkami."""
    if isinstance(blok, dict):
        return ["%s=%s" % (k, v) for k, v in blok.items()]
    return [str(x) for x in (blok or [])]


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

        # Labelki Traefika MUSZĄ być w deploy.labels. Przy `docker stack deploy`
        # labelki z poziomu usługi trafiają do KONTENERÓW, a provider swarm czyta
        # labelki USŁUGI — wtedy Traefik nie widzi żadnego routera, domena zwraca
        # 404 z domyślnym certyfikatem, a `docker stack config` i walidacja YAML
        # przechodzą bez słowa. Zmierzone na produkcji 2026-09-22.
        if any("traefik." in l for l in etykiety(s.get("labels"))):
            bledy.append(f"{nazwa}: labelki traefik.* na poziomie usługi "
                         f"(mają być w deploy.labels, inaczej provider swarm ich nie widzi)")

        w_deploy = etykiety((s.get("deploy") or {}).get("labels"))
        if any("traefik." in l for l in w_deploy) and not any(l.startswith("traefik.enable=true") for l in w_deploy):
            bledy.append(f"{nazwa}: labelki Traefika bez traefik.enable=true")

    if bledy:
        for b in bledy:
            print(f"  ✗ {b}")
        return 1
    print("  ✓ wszystkie zasady stacku spełnione")
    return 0


if __name__ == "__main__":
    sys.exit(main())
