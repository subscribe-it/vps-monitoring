#!/usr/bin/env python3
"""Każdy alert musi mieć procedurę w docs/RUNBOOK.md (inaczej: alert bez runbooka)."""
import glob
import re
import sys

WZORZEC = re.compile(r'runbook:\s*"#([a-z0-9]+)"')


def main() -> int:
    runbook = open("docs/RUNBOOK.md", encoding="utf-8").read()
    kotwice = set(re.findall(r'<a name="([a-z0-9]+)">', runbook))
    braki = []
    for wzor in ("config/prometheus/alerts/*.yml", "config/loki/rules/**/*.yml"):
        for plik in glob.glob(wzor, recursive=True):
            for dopasowanie in WZORZEC.finditer(open(plik, encoding="utf-8").read()):
                if dopasowanie.group(1) not in kotwice:
                    braki.append(f"{plik}: brak sekcji #{dopasowanie.group(1)}")
    if braki:
        for b in sorted(set(braki)):
            print(f"  ✗ {b}")
        return 1
    print(f"  ✓ wszystkie alerty mają procedury ({len(kotwice)} sekcji runbooka)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
