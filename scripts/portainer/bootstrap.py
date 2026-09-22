#!/usr/bin/env python3
"""Sterowanie stackiem monitoringu przez API Portainera (wołane z GitHub Actions).

Po co: po zbudowaniu obrazów GitHub Actions ma wywołać redeploy stacku, a przy
pierwszym uruchomieniu — sprawdzić i wystartować stack. Publiczny webhook stacka
da się utworzyć tylko w UI Portainera (API 2.33 nie ma trasy tworzącej webhook
stacka — sprawdzone w źródłach i na żywym Portainerze 2.33), natomiast
uwierzytelnione `PUT /api/stacks/{id}/git/redeploy` robi to samo i nie wymaga
publicznego adresu.

Co potrafi:
  --check     (domyślnie) połącz, znajdź stack, sprawdź ścieżkę compose i status
  --start     wystartuj stack, jeśli stoi
  --redeploy  wymuś pobranie z Gita i wdrożenie (z zachowaniem Env stacka!)

Czego NIE robi: nie zmienia ścieżki do pliku compose. API 2.33 pozwala ustawić
ją tylko przy tworzeniu stacka (`ComposeFile` w payloadzie tworzenia z repo),
a `POST /stacks/{id}/git` zmienia wyłącznie ustawienia repozytorium. Jeśli stack
wskazuje inny plik niż `docker-compose.yml`, skrypt kończy się kodem 2 i mówi,
co zrobić w UI.

Użycie:
    PORTAINER_URL=https://portainer.example:9443 PORTAINER_API_KEY=ptr_xxx \
        python3 scripts/portainer/bootstrap.py [--stack monitoring] [--start] [--redeploy]
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

STACK = os.environ.get("PORTAINER_STACK", "monitoring")
# Ścieżka w repo, na którą MUSI wskazywać stack (ta sama, którą waliduje CI).
COMPOSE = os.environ.get("PORTAINER_COMPOSE", "docker-compose.yml")


def klient(url, klucz):
    """Zwraca funkcję wołającą API. Klucz może być tokenem API albo JWT."""
    kontekst = ssl.create_default_context()
    kontekst.check_hostname = False
    kontekst.verify_mode = ssl.CERT_NONE  # Portainer często ma certyfikat self-signed
    baza = url.rstrip("/")
    naglowki = {"Content-Type": "application/json"}
    if klucz.count(".") == 2:  # JWT (tak wygląda token z /api/auth)
        naglowki["Authorization"] = "Bearer %s" % klucz
    else:
        naglowki["X-API-Key"] = klucz

    def wolaj(metoda, sciezka, dane=None, surowy=False):
        cialo = json.dumps(dane).encode() if dane is not None else None
        req = urllib.request.Request(baza + sciezka, data=cialo, method=metoda, headers=naglowki)
        try:
            with urllib.request.urlopen(req, timeout=30, context=kontekst) as odp:
                bajty = odp.read()
                if surowy:
                    # Logi Dockera to strumień z ramkami binarnymi — dekodowanie
                    # ich do tekstu psuje długości ramek (bajty >127 stają się
                    # znakami zastępczymi i licznik się rozjeżdża).
                    return odp.status, bajty
                tresc = bajty.decode("utf-8", "replace")
                if not tresc.strip():
                    return odp.status, tresc
                try:
                    return odp.status, json.loads(tresc)
                except json.JSONDecodeError:
                    return odp.status, tresc
        except urllib.error.HTTPError as e:
            tresc = e.read().decode("utf-8", "replace")
            try:
                tresc = json.loads(tresc)
            except json.JSONDecodeError:
                pass
            return e.code, tresc

    return wolaj


def odfiltruj_logi(surowy):
    """Docker skleja logi w ramki: 8-bajtowy nagłówek (typ + długość) i treść.

    Bez zdjęcia nagłówków w logu widać śmieci w rodzaju „\\x01\\x00\\x00\\x00".
    """
    wynik, i = [], 0
    bajty = surowy.encode("utf-8", "surrogateescape") if isinstance(surowy, str) else surowy
    while i < len(bajty):
        if bajty[i] in (0, 1, 2) and bajty[i + 1:i + 4] == b"\x00\x00\x00":
            dlugosc = int.from_bytes(bajty[i + 4:i + 8], "big")
            wynik.append(bajty[i + 8:i + 8 + dlugosc].decode("utf-8", "replace"))
            i += 8 + dlugosc
        else:  # strumień bez ramek (tty)
            wynik.append(bajty[i:].decode("utf-8", "replace"))
            break
    return "".join(wynik)


def uslugi_stacku(api, eid, przestrzen):
    """Lista usług stacku z liczbą zadań w stanie running."""
    filtr = urllib.parse.quote(json.dumps({"label": ["com.docker.stack.namespace=%s" % przestrzen]}))
    kod, uslugi = api("GET", f"/api/endpoints/{eid}/docker/services?filters={filtr}")
    if kod != 200:
        raise SystemExit(f"  ✗ nie mogę wylistować usług: HTTP {kod} {uslugi}")
    kod, zadania = api("GET", f"/api/endpoints/{eid}/docker/tasks?filters={filtr}")
    if kod != 200:
        raise SystemExit(f"  ✗ nie mogę wylistować zadań: HTTP {kod} {zadania}")
    licznik = {}
    bledy = {}
    for z in zadania or []:
        sid = z.get("ServiceID")
        stan = (z.get("Status") or {}).get("State") or "?"
        if stan == "running":
            licznik[sid] = licznik.get(sid, 0) + 1
        else:
            opis = (z.get("Status") or {}).get("Err") or ""
            if not opis:
                opis = "%s (stan: %s)" % ((z.get("DesiredState") or "?"), stan)
            bledy.setdefault(sid, opis)
    return uslugi or [], licznik, bledy


def pokaz_uslugi(api, eid, przestrzen):
    uslugi, licznik, bledy = uslugi_stacku(api, eid, przestrzen)
    ok = 0
    print(f"  usług w stacku: {len(uslugi)}")
    for u in sorted(uslugi, key=lambda x: (x.get("Spec") or {}).get("Name", "")):
        nazwa = (u.get("Spec") or {}).get("Name", "?")
        chce = ((u.get("Spec") or {}).get("Mode") or {}).get("Replicated") or {}
        chce = chce.get("Replicas", 1)
        ma = licznik.get(u.get("ID"), 0)
        pelne = ma >= chce
        ok += 1 if pelne else 0
        znacznik = "✓" if pelne else "✗"
        print(f"    {znacznik} {nazwa:38s} {ma}/{chce}")
        if not pelne and u.get("ID") in bledy:
            print(f"        powód: {bledy[u['ID']][:150]}")
    print(f"  z pełnymi replikami: {ok}/{len(uslugi)}")
    return ok == len(uslugi)


def znajdz_stack(api, nazwa):
    kod, dane = api("GET", "/api/stacks")
    if kod != 200:
        raise SystemExit(f"  ✗ nie mogę wylistować stacków: HTTP {kod} {dane}")
    for s in dane or []:
        if s.get("Name") == nazwa:
            return s
    widoczne = sorted(x.get("Name") for x in (dane or []))
    raise SystemExit(f"  ✗ nie ma stacku o nazwie „{nazwa}”. Widzę: {widoczne}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stack", default=STACK)
    p.add_argument("--compose", default=COMPOSE)
    p.add_argument("--start", action="store_true", help="wystartuj stack, jeśli stoi")
    p.add_argument("--redeploy", action="store_true", help="wymuś redeploy z Gita")
    p.add_argument("--pull", action="store_true", help="przy redeployu dociągnij obraz na nowo")
    p.add_argument("--json", action="store_true", help="wypisz wynik maszynowo")
    p.add_argument("--show-env", action="store_true",
                   help="pokaż NAZWY zmiennych środowiskowych stacka (wartości nigdy)")
    p.add_argument("--uslugi", action="store_true",
                   help="pokaż usługi stacku z liczbą działających replik i powodami awarii")
    p.add_argument("--logi", metavar="WZORZEC",
                   help="pokaż ostatnie linie logów usługi pasującej do wzorca (dowolny stack)")
    p.add_argument("--linii", type=int, default=40, help="ile linii logu (domyślnie 40)")
    args = p.parse_args()

    url = (os.environ.get("PORTAINER_URL") or "").strip()
    klucz = (os.environ.get("PORTAINER_API_KEY") or "").strip()
    if not url or not klucz:
        print("  ✗ potrzebne PORTAINER_URL i PORTAINER_API_KEY")
        return 1
    api = klient(url, klucz)

    kod, status = api("GET", "/api/system/status")
    if kod != 200:
        print(f"  ✗ brak połączenia z API Portainera ({url}): HTTP {kod} {status}")
        return 1
    print(f"  Portainer {status.get('Version')} — połączono ✓")

    stack = znajdz_stack(api, args.stack)
    sid, eid = stack.get("Id"), stack.get("EndpointId")
    plik = stack.get("EntryPoint") or stack.get("ComposeFile") or "?"
    dziala = (stack.get("Status") or 0) == 1
    print(f"  stack „{args.stack}”: id={sid}, endpoint={eid}, "
          f"status={'działa' if dziala else 'zatrzymany'}")

    if args.show_env:
        # Tylko NAZWY — wartości to sekrety (hasła, tokeny), nie mogą trafić do logu.
        env = stack.get("Env") or []
        nazwy = sorted(p.get("name") for p in env if isinstance(p, dict))
        puste = sorted(p.get("name") for p in env
                       if isinstance(p, dict) and not str(p.get("value") or "").strip())
        print(f"  zmiennych środowiskowych: {len(env)}")
        print(f"  nazwy: {', '.join(nazwy) if nazwy else '(brak)'}")
        if puste:
            print(f"  PUSTE wartości: {', '.join(puste)}")
        wymagane = ["PANEL_AUTH_PASSWORD_HTPASSWD", "GRAFANA_ADMIN_PASSWORD",
                    "NTFY_TOPIC", "NOTIFIER_TOKEN", "DOCKER_GID"]
        brakujace = [k for k in wymagane if k not in nazwy]
        if brakujace:
            print(f"  ✗ brakuje kluczowych zmiennych: {', '.join(brakujace)}")
        elif puste:
            print("  ! część zmiennych ma puste wartości — uzupełnij przed wdrożeniem")
        else:
            print("  ✓ komplet kluczowych zmiennych jest w stacku")

    if plik != args.compose:
        print(f"  ✗ stack wskazuje na „{plik}”, a powinien na „{args.compose}”.")
        print("    API Portainera nie pozwala zmienić tej ścieżki (ustawia się ją przy tworzeniu")
        print("    stacka). Popraw w UI: Stacks → %s → usuń i utwórz ponownie z repo," % args.stack)
        print(f"    ustawiając compose path = {args.compose}. Zmienne środowiskowe wklej")
        print("    z env.portainer.paste.txt. Potem uruchom ten workflow ponownie.")
        return 2
    print(f"  ścieżka compose: {plik} ✓")

    if args.uslugi:
        print()
        pokaz_uslugi(api, eid, args.stack)

    if args.logi:
        # Szukamy po WSZYSTKICH usługach w rojniku — dzięki temu można zajrzeć
        # także do Traefika z innego stacka (diagnostyka routingu).
        filtr = urllib.parse.quote(json.dumps({"name": [args.logi]}))
        kod, uslugi = api("GET", f"/api/endpoints/{eid}/docker/services?filters={filtr}")
        if kod != 200 or not uslugi:
            print(f"  ✗ nie znalazłem usługi pasującej do „{args.logi}”")
        else:
            for u in uslugi[:3]:
                nazwa = (u.get("Spec") or {}).get("Name")
                print(f"\n  --- log: {nazwa} (ostatnie {args.linii} linii) ---")
                kod, surowy = api("GET",
                    f"/api/endpoints/{eid}/docker/services/{u['ID']}/logs"
                    f"?stdout=1&stderr=1&timestamps=0&tail={args.linii}", surowy=True)
                if kod != 200:
                    print(f"    ✗ HTTP {kod}: {str(surowy)[:200]}")
                else:
                    for linia in odfiltruj_logi(surowy).splitlines():
                        print(f"    {linia[:220]}")

    if args.start and not dziala:
        # `endpointId` jest wymagane (bez niego Portainer zwraca 400) — sprawdzone
        # na żywym API 2.33: {"message":"Invalid query parameter: endpointId"}.
        kod, odp = api("POST", f"/api/stacks/{sid}/start?endpointId={eid}")
        print(f"  start stacku → HTTP {kod} {'✓' if kod == 200 else '✗ ' + str(odp)[:200]}")
        dziala = kod == 200

    if args.redeploy:
        # Env MUSI wrócić w payloadzie: pole jest nadpisywane tym, co przyślemy,
        # więc pusta lista skasowałaby zmienne środowiskowe stacka.
        env = stack.get("Env") or []
        cialo = {
            "RepositoryReferenceName": stack.get("RepositoryReferenceName") or "refs/heads/main",
            "RepositoryAuthentication": bool(stack.get("RepositoryAuthentication")),
            "RepositoryUsername": stack.get("RepositoryUsername") or "",
            "RepositoryPassword": "",
            "Env": env,
            "Prune": True,
            "PullImage": bool(args.pull),
            "StackName": stack.get("Name"),
        }
        kod, odp = api("PUT", f"/api/stacks/{sid}/git/redeploy", cialo)
        ok = kod == 200
        print(f"  redeploy z Gita → HTTP {kod} {'✓' if ok else '✗ ' + str(odp)[:200]}")
        print(f"    (przekazano {len(env)} zmiennych środowiskowych stacka)")
        if not ok:
            return 3

    if args.json:
        print(json.dumps({"id": sid, "endpoint": eid, "compose": plik,
                          "running": dziala, "url": url.rstrip("/")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
