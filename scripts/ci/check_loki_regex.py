#!/usr/bin/env python3
r"""Wykrywa wzorce LogQL, które w Loki 3.x dopasowują NIC (cicha awaria).

Dwa zmierzone przypadki (patrz docs/VERIFICATION.md, sekcja o martwych gałęziach):

1. `X.*(a|b)` — kropka-gwiazdka BEZPOŚREDNIO przed grupą z alternacją.
   Loki przyjmuje taki regex i nie dopasowuje ani `a`, ani `b`, ani nic innego.
   Bez błędu, bez wpisu w logu — reguła jest trwale martwa, a wygląda poprawnie.
   Obejście: `X.{0,80}(a|b)` albo wstawić znak między `.*` a grupę (`X.* (a|b)`).

2. `\\.` (podwójny backslash) w filtrze `|~ "…"`. Loki NIE przekazuje escape'ów
   do silnika regexów: wzorzec `\\.` wymaga w logu znaku backslash, więc nigdy
   nie pasuje. Piszemy klasę znaku: `[.]`.

3. `\.` (backslash przed znakiem, który nie jest escape'em w łańcuchu LogQL) —
   to BŁĄD SKŁADNI: ruler odrzuca **cały plik reguł** ("invalid char escape").
   Loki wstaje, `-verify-config` przechodzi, YAML jest poprawny, a alerty z tego
   pliku nie istnieją. Zamiast `\.` pisz `[.]`, zamiast `\d` — `[0-9]`.

Wszystkie trzy przeszłyby walidację składni, dlatego pilnuje ich ten skrypt,
a `check_ruler_loaded.py` sprawdza dodatkowo, ile reguł ruler FAKTYCZNIE wczytał.
"""
import glob
import json
import os
import re
import sys

KATALOGI = ["config/loki", "config/grafana", "config/prometheus"]


def wzorce_z_yaml(sciezka):
    """Wszystkie filtry `|~ "…"` z plików reguł (i innych YAML-i z LogQL)."""
    try:
        import yaml
    except ImportError:
        return []
    wzorce = []
    with open(sciezka, encoding="utf-8") as f:
        tresc = f.read()
    if "|~" not in tresc:
        return []
    try:
        dane = yaml.safe_load(tresc)
    except yaml.YAMLError:
        return []
    def chodz(wezel):
        if isinstance(wezel, dict):
            for v in wezel.values():
                chodz(v)
        elif isinstance(wezel, list):
            for v in wezel:
                chodz(v)
        elif isinstance(wezel, str):
            wzorce.extend(re.findall(r'\|~\s*"((?:[^"\\]|\\.)*)"', wezel))
    chodz(dane)
    return wzorce


def wzorce_z_json(sciezka):
    """Zapytania LogQL z dashboardów Grafany."""
    with open(sciezka, encoding="utf-8") as f:
        try:
            dane = json.load(f)
        except json.JSONDecodeError:
            return []
    wzorce = []
    def chodz(wezel):
        if isinstance(wezel, dict):
            for v in wezel.values():
                chodz(v)
        elif isinstance(wezel, list):
            for v in wezel:
                chodz(v)
        elif isinstance(wezel, str):
            wzorce.extend(re.findall(r'\|~\s*"((?:[^"\\]|\\.)*)"', wezel))
    chodz(dane)
    return wzorce


def niepoprawny_escape(wzorzec):
    """Zwraca pierwszy niepoprawny escape w łańcuchu LogQL albo None.

    LogQL w cudzysłowie zna tylko `\\\\`, `\\"`, `\\n`, `\\t`, `\\r`. Każdy inny
    (`\\.`, `\\d`, `\\s`) to błąd składni, który wywala CAŁY plik reguł.
    """
    i = 0
    while i < len(wzorzec):
        if wzorzec[i] == "\\":
            if i + 1 >= len(wzorzec):
                return "\\"
            nastepny = wzorzec[i + 1]
            if nastepny not in ('\\', '"', "n", "t", "r"):
                return "\\" + nastepny
            i += 2
            continue
        i += 1
    return None


def main() -> int:
    pliki = []
    for katalog in KATALOGI:
        pliki += glob.glob(os.path.join(katalog, "**", "*.yml"), recursive=True)
        pliki += glob.glob(os.path.join(katalog, "**", "*.yaml"), recursive=True)
        pliki += glob.glob(os.path.join(katalog, "**", "*.json"), recursive=True)

    bledy = []
    ile = 0
    for plik in sorted(set(pliki)):
        wzorce = wzorce_z_yaml(plik) if plik.endswith((".yml", ".yaml")) else wzorce_z_json(plik)
        for w in wzorce:
            ile += 1
            if ".*(" in w:
                bledy.append((plik, w, "`.*(` — Loki nie dopasuje NICZEGO; użyj `.{0,80}(`"))
            if "\\\\" in w:
                bledy.append((plik, w, "podwójny backslash — Loki przekazuje go do regexu dosłownie; użyj `[.]`"))
            zly = niepoprawny_escape(w)
            if zly:
                bledy.append((plik, w,
                              f"niepoprawny escape `{zly}` w łańcuchu LogQL — ruler odrzuci CAŁY plik reguł; "
                              f"użyj klasy znaku (np. `[.]` zamiast `\\.`)"))

    print(f"  przejrzano {ile} wzorców LogQL w {len(set(pliki))} plikach")
    if bledy:
        print()
        for plik, w, powod in bledy:
            print(f"  ✗ {plik}")
            print(f"      {powod}")
            print(f"      wzorzec: {w[:100]}")
        print()
        print(f"  BŁĄD: {len(bledy)} niebezpiecznych wzorców LogQL.")
        return 1
    print("  ✓ brak `.*(`, podwójnych backslashów i niepoprawnych escape'ów")
    return 0


if __name__ == "__main__":
    sys.exit(main())
