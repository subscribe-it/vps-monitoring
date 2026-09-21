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
