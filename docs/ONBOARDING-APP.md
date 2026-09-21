# Dodanie nowej aplikacji

## Domyślny przypadek: nic nie musisz robić

1. Tworzysz stack w Portainerze z routingiem Traefika (`Host(\`twoja-domena\`)`).
2. W ciągu ~30–60 sekund:
   - `discovery` wykrywa usługę i jej trasę,
   - Prometheus zaczyna sonduć adres (HTTP SD — bez restartu i bez edycji plików),
   - logi kontenerów trafiają do Lokiego (`docker_sd_configs`),
   - kafelek pojawia się w panelu, pogrupowany po stacku,
   - przychodzi informacja `SwarmNewServiceDiscovered` — potwierdzenie pokrycia.

Od tej chwili automatycznie działają: `AppDown`, `AppSlow`, `TlsCertExpiringSoon`,
`SwarmServiceReplicasMismatch`, `SwarmServiceTasksFailing`, `SwarmContainerUnhealthy`,
`SwarmContainerHighMemory`, a logi są przeszukiwalne.

**Poziom istotności nowej aplikacji to domyślnie `warning`** (tylko e-mail, bez
budzenia w nocy). Jeśli stack ma dzwonić pushem, dopisz go do `CRITICAL_STACKS`
w env stacku `monitoring` **albo** dodaj label `monitoring.io/severity=critical`.

## Gdy chcesz coś nadpisać (labele usługi)

Dodaj label do usługi w Portainerze (sekcja *Labels* przy edycji stacku):

| Label | Przykład | Efekt |
| --- | --- | --- |
| `monitoring.io/skip` | `true` | nie monitoruj tej usługi wcale |
| `monitoring.io/health-path` | `/api/health/ready` | sonduj tę ścieżkę zamiast `/` |
| `monitoring.io/probe` | `https://api.example.com/health` | pełny adres sondy (nadpisuje wykryty z Traefika) |
| `monitoring.io/severity` | `critical` / `warning` / `skip` | kto dzwoni w nocy |
| `monitoring.io/module` | `http_expect_auth` | moduł sondy blackboxa |
| `monitoring.io/name` | `Sklep — produkcja` | czytelna nazwa w panelu |

Dostępne moduły sond: `http_2xx` (domyślny), `http_2xx_3xx` (przekierowania),
`http_expect_auth` (oczekuje 401 — dla paneli za logowaniem), `http_alive`
(2xx/3xx/401/403), `tcp_connect`.

## Aplikacja bez routingu Traefika (worker, kolejka, baza)

Dostaje monitoring kontenerowy: repliki, nieudane zadania, zasoby, zdrowie, logi.
Nie ma sondy HTTP, bo nie ma czego sondować — chyba że dodasz
`monitoring.io/probe`.

## Aplikacje, które mają być pominięte na stałe

- `DISCOVERY_SKIP_STACKS` — całe stacki (domyślnie `monitoring,traefik,traefik_stack`,
  gdzie `traefik` to pozostałości po starym edge, a nie działająca aplikacja),
- label `monitoring.io/skip=true` — pojedyncza usługa.

## Weryfikacja, że nowa aplikacja jest objęta monitoringiem

```bash
curl -s http://<host>/sd/http.json            # z wnętrza sieci monitoring
curl -s https://monitoring.subscribeit.pl/status/api.json | grep -A3 '<nazwa-stacka>'
```
albo po prostu: panel → sekcja „Stacki" i Prometheus → Status → Targets.
