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
import urllib.request

OCZEKIWANE = int(os.environ.get("OCZEKIWANE_USLUGI", "12"))
BUDZET_SEKUND = int(os.environ.get("CZAS_NA_WDROZENIE", "240"))
PREFIX = os.environ.get("PREFIX_USLUG", "monitoring_")
ADRES = os.environ["PORTAINER_URL"].rstrip("/")
KLUCZ = os.environ["PORTAINER_API_KEY"]


def pobierz(sciezka):
    zapytanie = urllib.request.Request(ADRES + sciezka, headers={"X-API-Key": KLUCZ})
    with urllib.request.urlopen(zapytanie, timeout=60) as odpowiedz:
        return json.load(odpowiedz)


granica = time.time() + BUDZET_SEKUND
stan = "brak danych"
while True:
    try:
        uslugi = [u for u in pobierz("/api/endpoints/1/docker/services")
                  if u["Spec"]["Name"].startswith(PREFIX)]
    except Exception as wyjatek:  # noqa: BLE001 - raportujemy, nie wywalamy się
        uslugi = []
        stan = f"API Portainera nie odpowiedziało: {type(wyjatek).__name__}"

    braki = []
    for usluga in uslugi:
        tryb = (usluga["Spec"].get("Mode") or {}).get("Replicated") or {}
        chcemy = int(tryb.get("Replicas", 1))
        mamy = int((usluga.get("ServiceStatus") or {}).get("RunningTasks", 0))
        if mamy < chcemy:
            braki.append(f"{usluga['Spec']['Name']} {mamy}/{chcemy}")

    if len(uslugi) >= OCZEKIWANE and not braki:
        print(f"  ✓ stack kompletny: {len(uslugi)} usług, wszystkie z pełnymi replikami")
        sys.exit(0)

    stan = f"usług: {len(uslugi)}/{OCZEKIWANE}" + (f" · bez pełnych replik: {', '.join(braki[:6])}" if braki else "")
    if time.time() > granica:
        print(f"  ✗ stack NIEkompletny po {BUDZET_SEKUND} s: {stan}")
        print("    Wdrożenie jest nieudane — sprawdź typ stacku (Swarm!), sieci i obrazy w Portainerze.")
        sys.exit(1)
    time.sleep(10)
