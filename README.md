# monitoring — stack obserwacyjny dla `ovh-vps-1`

Kompletny monitoring infrastruktury z **automatycznym wykrywaniem nowych aplikacji**.
Wdrażany w całości z tego repozytorium przez GitHub Actions → Portainer.

> **Zasada nadrzędna:** ten stack wyłącznie **obserwuje**. Nie modyfikuje żadnego
> innego stacka na tym hoście. Szczegóły i granice: [`docs/SCOPE.md`](docs/SCOPE.md).

## Co tu jest

| Warstwa | Co pokrywa |
| --- | --- |
| **Dostępność** | sondy HTTP każdej publicznej domeny + własnego łańcucha (DNS → cert → Traefik → auth) |
| **Certyfikaty** | wygasanie TLS (< 14 dni, < 3 dni) i błędy ACME z logów edge |
| **Host** | dysk, i-węzły, RAM, PSI, OOM, load, zegar, restarty, błędy I/O jądra |
| **Swarm** | repliki `N/N`, zadania `rejected`, pętle restartów, `unhealthy`, limity pamięci |
| **Baza (z logów)** | `page verification failed`, PANIC, brak miejsca, wyczerpane połączenia |
| **Backupy** | wiek ostatniego dumpu, zaległy test odtworzenia, dostarczalność powiadomień |
| **Logi** | centralne zbieranie (kontenery + journald + access log Traefika) i reguły logowe |
| **Bezpieczeństwo** | logowania SSH/Cockpit, skoki nieudanych prób, bany fail2bana |
| **Zewnętrznie** | watchdog healthchecks.io — cisza z VPS oznacza alarm |

Kanał alertów: **ntfy** (push na telefon) + **e-mail** (zapas i dziennik).
Hałasuje tylko `critical`; `warning`/`info` przychodzą jako ciche powiadomienia.
| **Jeden widok** | panel `monitoring.subscribeit.pl` z kafelkami i żywym stanem + Grafana |

## Jak to działa w skrócie

1. **`discovery`** co 30 s czyta Docker API (tylko `GET`, socket `:ro`) i wyciąga
   z labeli Traefika wszystkie trasy `Host(...)`.
2. Wystawia je Prometheusowi przez **HTTP Service Discovery** → nowa aplikacja
   w Portainerze **sama** zaczyna być sondowana (bez edycji plików, bez restartu).
3. Ten sam serwis buduje `/status/api.json`, z którego panel rysuje kafelki —
   nowa aplikacja pojawia się na stronie startowej automatycznie.
4. Alerty z Prometheusa i z Lokiego trafiają do Alertmanagera, a stamtąd do
   **`notifier`**, który wysyła push (ntfy) i e-mail.
5. **`health-ping`** pinguje healthchecks.io **tylko wtedy, gdy wszystko jest
   zielone** — brak pingu to jedyny sygnał, który zadziała także przy śmierci hosta.

## Szybki start

Wdrożenie krok po kroku: [`DEPLOY.md`](DEPLOY.md).
Adresy i logowanie: [`ACCESS.md`](ACCESS.md).

## Dokumentacja

| Plik | Zawartość |
| --- | --- |
| [`docs/SCOPE.md`](docs/SCOPE.md) | zasada nadrzędna, co wolno, granice wiedzy |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | przepływ, komponenty, auto-discovery, poziomy istotności |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | co robić przy każdym alercie (24 procedury) |
| [`docs/ONBOARDING-APP.md`](docs/ONBOARDING-APP.md) | jak dodać nową aplikację i co stanie się samo |
| [`docs/STATUS-API.md`](docs/STATUS-API.md) | kontrakt `/status/api.json` dla panelu |
| [`docs/BASELINE.md`](docs/BASELINE.md) | stan hosta i aplikacji z dnia rozpoznania |
| [`env.portainer.example`](env.portainer.example) | komplet zmiennych do wklejenia w Portainera |

## Test lokalny (przed pushem)

Cały stack można podnieść na własnym komputerze — **tak został znaleziony realny błąd**
(`--web.enable-admin-api=false` wysadzał Prometheusa w pętli restartów, czego nie widzi
żadna walidacja statyczna).

```bash
make validate   # compose, promtool (config + reguły + testy reguł), Loki, Grafana, testy Pythona
make build      # zbuduj wszystkie 10 obrazów lokalnie
make up         # podnieś stack (projekt monlocal, wymaga /tmp/mon-local)
make ps         # stan usług
make down       # sprzątanie
```

Reguły logowe mają własne, twarde kontrole (bo dwie ciche awarie przeszły przez
wszystkie walidacje statyczne — patrz `docs/VERIFICATION.md`):

```bash
python3 scripts/ci/check_loki_regex.py     # wzorce, które w Loki dopasują NIC
python3 tests/integration/verify_log_patterns.py   # każda gałąź regexu vs realna linia (wymaga Loki)
LOKI_URL=… python3 scripts/ci/check_ruler_loaded.py # ile reguł ruler FAKTYCZNIE wczytał
python3 tests/integration/verify_ntfy_real.py       # prawdziwy ntfy.sh: czy powiadomienie dochodzi (wymaga internetu)

Przygotowanie zmiennych do Portainera (generuje hash hasła, losowe sekrety
i wypisuje gotowy blok `KLUCZ=WARTOŚĆ` do wklejenia):

```bash
scripts/przygotuj-env.sh                    # tryb interaktywny, pyta o wszystko
scripts/przygotuj-env.sh --plik /tmp/env.txt
```
```

Uwagi do środowiska lokalnego: `discovery` potrzebuje **menedżera Swarma** (na zwykłym
demonie `/services` zwraca 503 → `discovery_up 0`, co jest poprawne), a sondy
`blackbox-monitoring` będą `down`, bo domena monitoringu nie ma tam jeszcze routingu.

## Wykresy

W Grafanze są cztery dashboardy przekrojowe (`VPS ovh-vps-1`, `Aplikacje`,
`Host`, `Logi`) oraz **„Ruch i obciążenie — per usługa i aplikacja"**: CPU, RAM,
ruch sieciowy (RX/TX w B/s), I/O dysku, repliki i nieudane zadania **na wybraną
usługę**, a obok ruch HTTP z access logów Traefika — żądania na minutę per
aplikacja i per usługa backendu, kody odpowiedzi, odsetek 5xx, p95 czasu
odpowiedzi i najczęstsze ścieżki.

## Struktura

```
docker-compose.yml        # jedyne źródło prawdy (12 usług, zero publikowanych portów)
dockerfiles/              # obrazy z konfiguracją wypaloną w środku
config/                   # prometheus (+alerts), loki (+rules), promtail, blackbox, grafana, auth, alertmanager
services/                 # discovery, notifier, health-ping (Python, tylko stdlib)
panel/                    # strona startowa (Astro + Tailwind + DaisyUI), statyczny build → nginx
tests/                    # testy jednostkowe serwisów
.github/workflows/        # validate → build images → deploy (webhook Portainera) → smoke test
docs/                     # dokumentacja powyżej
```

## Wymagane sekrety GitHub

| Sekret | Do czego |
| --- | --- |
| `PORTAINER_MONITORING_WEBHOOK` | wywołanie redeployu stacku po zbudowaniu obrazów |
| `NOTIFIER_TOKEN` (opcjonalnie) | powiadomienie na telefon, gdy deploy się nie powiedzie |
