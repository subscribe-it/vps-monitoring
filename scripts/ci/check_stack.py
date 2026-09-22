#!/usr/bin/env python3
"""Kontrola kompletności stacku po wdrożeniu.

Powód istnienia (zmierzone 22.09.2026): wdrożenie raportowało sukces, a stack
miał ZERO usług. Ówczesny smoke test sprawdzał tylko kod 401 na domenie, więc
pusty stack (404) przechodził jako sukces. Ten test pyta Swarma wprost.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

OCZEKIWANE = int(os.environ.get("OCZEKIWANE_USLUGI", "12"))
BUDZET_SEKUND = int(os.environ.get("CZAS_NA_WDROZENIE", "240"))
PREFIX = os.environ.get("PREFIX_USLUG", "monitoring_")
# Zawór testowy: wymusza ścieżkę liczenia zadań (dowód, że fallback działa).
IGNORUJ_STAN = os.environ.get("IGNORUJ_STAN_USLUG") == "1"


def zmienna(nazwa: str) -> str:
    """Czyta zmienną środowiskową i mówi wprost, czego brakuje.

    Bez tego brak bloku `env:` w kroku CI kończył się KeyError-em, którego
    komunikat nie mówi, co poprawić.
    """
    wartosc = os.environ.get(nazwa)
    if not wartosc:
        sys.exit(
            f"✗ brak {nazwa} w środowisku — ten test pyta API Portainera "
            "(w CI: sekrety PORTAINER_URL / PORTAINER_API_KEY w bloku env kroku)"
        )
    return wartosc


ADRES = zmienna("PORTAINER_URL").rstrip("/")
KLUCZ = zmienna("PORTAINER_API_KEY")


def pobierz(sciezka):
    zapytanie = urllib.request.Request(ADRES + sciezka, headers={"X-API-Key": KLUCZ})
    with urllib.request.urlopen(zapytanie, timeout=60) as odpowiedz:
        return json.load(odpowiedz)


granica = time.time() + BUDZET_SEKUND
stan = "brak danych"
while True:
    try:
        uslugi = [u for u in pobierz("/api/endpoints/1/docker/services?status=true")
                  if u["Spec"]["Name"].startswith(PREFIX)]
    except Exception as wyjatek:  # noqa: BLE001 - raportujemy, nie wywalamy się
        uslugi = []
        stan = f"API Portainera nie odpowiedziało: {type(wyjatek).__name__}"

    braki = []
    chcemy_wg_nazwy: dict[str, int] = {}
    bez_licznika: dict[str, str] = {}  # nazwa -> ID usługi
    for usluga in uslugi:
        nazwa = usluga["Spec"]["Name"]
        tryb = (usluga["Spec"].get("Mode") or {}).get("Replicated") or {}
        chcemy = int(tryb.get("Replicas", 1))
        chcemy_wg_nazwy[nazwa] = chcemy
        status = usluga.get("ServiceStatus")
        if status is None or IGNORUJ_STAN:
            # Docker zwraca ServiceStatus tylko z ?status=true. Bez tego każda
            # usługa wygląda na 0/1 — fałszywy alarm zmierzony 22.09.2026 na
            # żywym, zdrowym stacku (12/12 działających usług).
            bez_licznika[nazwa] = usluga["ID"]
            continue
        mamy = int(status.get("RunningTasks", 0))
        if mamy < chcemy:
            braki.append(f"{nazwa} {mamy}/{chcemy}")

    # Brak licznika w odpowiedzi nie może ani udawać sukcesu, ani dawać
    # fałszywego alarmu: liczymy wtedy zadania wprost.
    if bez_licznika:
        filtr = urllib.parse.quote(
            json.dumps({"service": {i: True for i in bez_licznika.values()}})
        )
        blad_api = ""
        try:
            zadania = pobierz(f"/api/endpoints/1/docker/tasks?filters={filtr}")
        except Exception as wyjatek:  # noqa: BLE001
            zadania = []
            blad_api = type(wyjatek).__name__
        zywe: dict[str, int] = {}
        for zadanie in zadania:
            if (zadanie.get("Status") or {}).get("State") == "running":
                identyfikator = zadanie.get("ServiceID", "")
                zywe[identyfikator] = zywe.get(identyfikator, 0) + 1
        for nazwa, identyfikator in bez_licznika.items():
            mamy = zywe.get(identyfikator, 0)
            if mamy < chcemy_wg_nazwy[nazwa]:
                dodatek = f" (API nie zwróciło stanu: {blad_api})" if blad_api else ""
                braki.append(f"{nazwa} {mamy}/{chcemy_wg_nazwy[nazwa]}{dodatek}")

    if len(uslugi) >= OCZEKIWANE and not braki:
        print(f"  ✓ stack kompletny: {len(uslugi)} usług, wszystkie z pełnymi replikami")
        sys.exit(0)

    stan = f"usług: {len(uslugi)}/{OCZEKIWANE}" + (f" · bez pełnych replik: {', '.join(braki[:6])}" if braki else "")
    if time.time() > granica:
        print(f"  ✗ stack NIEkompletny po {BUDZET_SEKUND} s: {stan}")
        print("    Wdrożenie jest nieudane — sprawdź typ stacku (Swarm!), sieci i obrazy w Portainerze.")
        sys.exit(1)
    time.sleep(10)
