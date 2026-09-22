#!/usr/bin/env python3
r"""Wylicza, które obrazy trzeba przebudować po danym pushu.

Po co: budowa 11 obrazów przy każdej zmianie to najdroższa pozycja w CI. Mapę
zależności (który obraz z czego korzysta) czytamy WPROST z Dockerfile'ów — z linii
`COPY` — więc nie może się rozjechać z rzeczywistością.

Wejście (env, ustawiane przez workflow):
    ZMIENIONE_PLIKI  lista plików oddzielona newline; brak/`ALL` = buduj wszystko
Wyjście:
    JSON macierzy dla `strategy.matrix.include` (na stdout; przy GITHUB_OUTPUT
    dopisuje też `macierz=...`).

Użycie lokalne:
    ZMIENIONE_PLIKI=$'config/auth/default.conf' python3 scripts/ci/plan_builds.py
"""
import glob
import json
import os
import re
import sys

# Co zmienia się w obrazie: katalog źródłowy COPY -> nazwa obrazu.
KATALOGI = ["dockerfiles", "services", "panel"]


def dockerfile_obrazu(katalog, nazwa):
    for kandydat in (f"{katalog}/{nazwa}/Dockerfile", f"{katalog}/{nazwa}.Dockerfile"):
        if os.path.isfile(kandydat):
            return kandydat
    return None


def kontekst(dockerfile, nazwa):
    """Kontekst budowy = katalog Dockerfile'a, z wyjątkiem `dockerfiles/*`,
    które budują się z korzenia repo (kopiują config/ i inne katalogi)."""
    if dockerfile.startswith("dockerfiles/"):
        return "."
    return dockerfile.rsplit("/", 1)[0]


def mapa_obrazow():
    """{nazwa: {'dockerfile':…, 'context':…, 'zrodla': {ścieżki źródłowe COPY}}}"""
    obrazy = {}
    # `dockerfiles/<nazwa>/…` i `services/<nazwa>/…`, ale panel ma Dockerfile
    # bezpośrednio w swoim katalogu (`panel/Dockerfile`) — inaczej wypadał z mapy.
    pliki = []
    for katalog in ("dockerfiles", "services"):
        pliki += sorted(glob.glob(f"{katalog}/*/Dockerfile"))
    pliki += sorted(glob.glob("panel/Dockerfile"))
    for dockerfile in pliki:
        katalog_dockerfile, nazwa = dockerfile.split("/")[0], dockerfile.split("/")[1]
        if dockerfile == "panel/Dockerfile":
            nazwa = "panel"
        tresc = open(dockerfile, encoding="utf-8").read()
        zrodla = set()
        for linia in tresc.splitlines():
            m = re.match(r"^\s*COPY\s+(?:--\S+\s+)*(\S+)", linia, re.I)
            if not m:
                continue
            zrodlo = m.group(1)
            if zrodlo.startswith(("http", "$")):
                continue
            zrodla.add(zrodlo.rstrip("/"))
        obrazy[nazwa] = {
            "name": nazwa,
            "dockerfile": dockerfile,
            "context": kontekst(dockerfile, nazwa),
            "zrodla": zrodla,
        }
    return obrazy


def obrazy_do_budowy(zmienione):
    """Nazwy obrazów, których dotyczy zmiana. Puste = nic nie trzeba budować."""
    obrazy = mapa_obrazow()
    if zmienione is None:  # nie wiemy, co się zmieniło — bezpiecznie: wszystko
        return sorted(obrazy)

    # Pliki, które wpływają na ZAWARTOŚĆ każdego obrazu (kontekst budowy).
    # Sama logika planowania (plan_builds.py) ani workflow tego nie robią —
    # ich zmiana nie wymaga przebudowy obrazów.
    globalne = {".dockerignore"}
    if any(p in globalne for p in zmienione):
        return sorted(obrazy)

    # `docker-compose.yml` wpływa na WDROŻENIE, nie na zawartość obrazów —
    # przebudowa 11 obrazów po zmianie samego compose to spalone minuty.
    if "docker-compose.yml" in zmienione:
        zmienione = [p for p in zmienione if p != "docker-compose.yml"]
        if not zmienione:
            return []

    do_budowy = set()
    for plik in zmienione:
        for nazwa, info in obrazy.items():
            if plik == info["dockerfile"]:
                do_budowy.add(nazwa)
                continue
            # plik z kontekstu obrazu (np. services/notifier/main.py)
            if plik.startswith(info["context"] + "/"):
                do_budowy.add(nazwa)
                continue
            # plik skopiowany do obrazu (np. config/auth/default.conf)
            for zrodlo in info["zrodla"]:
                if plik == zrodlo or plik.startswith(zrodlo + "/"):
                    do_budowy.add(nazwa)
                    break
    return sorted(do_budowy)


def czy_wdrazac(zmienione, ile_obrazow):
    """Wdrożenie ma sens, gdy zbudowano obrazy albo zmienił się docker-compose.yml.

    Zmiana samego workflowu czy skryptu CI nie wymaga ani budowy, ani redeployu —
    a redeploy to i tak kilka minut (pull + smoke test).
    """
    if zmienione is None or ile_obrazow > 0:
        return True
    return "docker-compose.yml" in zmienione


def main() -> int:
    surowe = (os.environ.get("ZMIENIONE_PLIKI") or "").strip()
    zmienione = None if (not surowe or surowe == "ALL") else [p for p in surowe.splitlines() if p.strip()]
    nazwy = obrazy_do_budowy(zmienione)
    obrazy = mapa_obrazow()
    macierz = [{"name": n, "dockerfile": obrazy[n]["dockerfile"], "context": obrazy[n]["context"]} for n in nazwy]
    wynik = json.dumps(macierz, separators=(",", ":"))
    print(wynik)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("macierz=%s\n" % wynik)
            f.write("ile=%d\n" % len(macierz))
            f.write("wdrazaj=%s\n" % ("true" if czy_wdrazac(zmienione, len(macierz)) else "false"))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### Obrazy do przebudowy: %d z %d\n\n" % (len(nazwy), len(obrazy)))
            f.write(", ".join(nazwy) if nazwy else "(nic — brak zmian w obrazach)")
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
