#!/usr/bin/env python3
"""Sprawdza, ile reguł ruler FAKTYCZNIE wczytał — nie ile ich leży w plikach.

Po co: plik reguł z niepoprawnym escape'em (`\\.` zamiast `[.]`) albo ze złą
składnią LogQL powoduje, że ruler **odrzuca cały plik**. Loki wstaje, `-verify-config`
przechodzi, YAML jest poprawny — a alerty z tego pliku nie istnieją. Ten skrypt
porównuje liczbę reguł w plikach z liczbą reguł zgłoszonych przez API rulera.

Użycie:
    LOKI_URL=http://127.0.0.1:3100 python3 scripts/ci/check_ruler_loaded.py
"""
import glob
import json
import os
import sys
import urllib.request

import yaml

LOKI = os.environ.get("LOKI_URL", "http://127.0.0.1:3100").rstrip("/")


def reguly_z_plikow():
    ile, grupy = 0, set()
    for plik in glob.glob("config/loki/rules/**/*.yml", recursive=True):
        with open(plik, encoding="utf-8") as f:
            dane = yaml.safe_load(f)
        for grupa in dane.get("groups", []):
            grupy.add(grupa.get("name"))
            ile += len(grupa.get("rules", []))
    return ile, grupy


def reguly_z_rulera():
    url = LOKI + "/prometheus/api/v1/rules"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            dane = json.load(r)
    except Exception as e:  # noqa: BLE001 — każdy błąd znaczy to samo: nie da się potwierdzić
        return None, None, str(e)
    grupy = dane.get("data", {}).get("groups", [])
    return sum(len(g.get("rules", [])) for g in grupy), {g.get("name") for g in grupy}, ""


def main() -> int:
    w_plikach, grupy_plikow = reguly_z_plikow()
    w_rulerze, grupy_rulera, blad = reguly_z_rulera()

    print(f"  Loki: {LOKI}")
    print(f"  w plikach:  {w_plikach} reguł w {len(grupy_plikow)} grupach")
    if w_rulerze is None:
        print(f"  ✗ nie udało się zapytać rulera: {blad}")
        return 1
    print(f"  w rulerze:  {w_rulerze} reguł w {len(grupy_rulera)} grupach")

    if w_rulerze != w_plikach:
        brak = sorted(g for g in grupy_plikow if g not in grupy_rulera)
        print()
        print(f"  ✗ RULER NIE WCZYTAŁ WSZYSTKICH REGUŁ (różnica: {w_plikach - w_rulerze})")
        if brak:
            print(f"    grupy nieobecne w rulerze: {brak}")
        print("    Sprawdź logi Loki: `unable to list rules` / `parse error`.")
        print("    Typowa przyczyna: niepoprawny escape w filtrze `|~ \"…\"` —")
        print("    w cudzysłowie `\\.` jest błędem składni; pisz `[.]` albo użyj backticków.")
        return 1

    print("  ✓ ruler wczytał wszystkie reguły z plików")
    return 0


if __name__ == "__main__":
    sys.exit(main())
