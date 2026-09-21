# Architektura

## Przepływ

```
                 ┌── ntfy.sh (push na telefon) ─────► Ty
notifier ◄───────┼── SMTP (e-mail, kanał zapasowy) ─► skrzynka
   ▲             └── healthchecks.io (watchdog) ─────► e-mail
   │ webhook
Alertmanager ◄─── Prometheus (reguły metryczne)
   ▲             └─ Loki Ruler (reguły logowe)
   │
health-ping ──► healthchecks.io: "vps-all-ok" (tylko gdy wszystko zielone)

Prometheus ◄── node-exporter (host)
           ◄── discovery (repliki usług, zadania, zasoby kontenerów)
           ◄── blackbox-exporter ◄── HTTP SD z discovery (nowe aplikacje!)
           ◄── health-ping, notifier, loki, promtail, grafana, alertmanager (samo-monitoring)

Promtail ──► Loki   (kontenery przez Docker API, journald hosta, access log Traefika)

monitoring.subscribeit.pl (Traefik + ForwardAuth, jedno logowanie)
   /            panel Astro (kafelki + iframes + żywy stan)
   /grafana     Grafana (serve_from_sub_path)
   /prometheus  Prometheus
   /alertmanager Alertmanager
   /status/api.json  discovery → dane dla panelu
```

## Komponenty

| Usługa | Rola | Obraz |
| --- | --- | --- |
| `auth` | ForwardAuth dla Traefika; sekret nigdy nie trafia do labeli | `vps-monitoring-auth` |
| `panel` | strona startowa z kafelkami i żywym stanem | `vps-monitoring-panel` |
| `discovery` | **serce auto-monitoringu**: Docker API → HTTP SD + metryki + `/status/api.json` | `vps-monitoring-discovery` |
| `prometheus` | metryki i reguły alertów | `vps-monitoring-prometheus` |
| `alertmanager` | routing, grupowanie, wyciszanie | `vps-monitoring-alertmanager` |
| `notifier` | jedyne wyjście alertów (ntfy + e-mail), ping watchdoga | `vps-monitoring-notifier` |
| `health-ping` | watchdog wychodzący do healthchecks.io | `vps-monitoring-health-ping` |
| `loki` | magazyn logów + ruler (alerty logowe) | `vps-monitoring-loki` |
| `promtail` | zbieranie logów z trzech źródeł | `vps-monitoring-promtail` |
| `blackbox-exporter` | sondy HTTP/TCP, wygasanie certyfikatów | `prom/blackbox-exporter` |
| `node-exporter` | metryki hosta | `prom/node-exporter` |
| `grafana` | dashboardy i przeglądanie logów | `vps-monitoring-grafana` |

Konfiguracja jest **wypalona w obrazach**, nie w Docker Swarm configs — dzięki temu
każda zmiana przechodzi przez Git i Actions, a redeploy nie zderza się z niezmiennymi
configami Swarma. Sekrety żyją wyłącznie w zmiennych środowiskowych stacka w Portainerze.

## Auto-discovery nowej aplikacji (bez żadnej konfiguracji)

1. Dodajesz aplikację w Portainerze (stack usług Swarma) z routingiem Traefika.
2. `discovery` (co 30 s) czyta `GET /services` i wyciąga z labeli `Host(...)` oraz `PathPrefix(...)`.
3. Nowy adres trafia do `GET /sd/http.json`, które Prometheus czyta przez `http_sd_configs`
   — nowy cel sondowania powstaje automatycznie, bez restartu i bez edycji plików.
4. Ten sam adres pojawia się w `/status/api.json`, więc **kafelek w panelu tworzy się sam**.
5. Logi nowych kontenerów łapie Promtail (`docker_sd_configs`) z etykietami stacka i usługi.
6. Alert `SwarmNewServiceDiscovered` potwierdza, że pokrycie zadziałało.

Nadpisania per usługa (labele w Portainerze):

| Label | Znaczenie |
| --- | --- |
| `monitoring.io/skip=true` | nie monitoruj tej usługi |
| `monitoring.io/probe=https://…` | własny adres sondy |
| `monitoring.io/health-path=/health` | zamiast `/` sonduj tę ścieżkę |
| `monitoring.io/severity=critical\|warning\|skip` | poziom istotności (kto dzwoni w nocy) |
| `monitoring.io/module=http_2xx` | moduł blackboxa |
| `monitoring.io/name=Nazwa` | czytelna nazwa w panelu |

## Poziomy istotności

- `critical` — push na telefon **i** e-mail; stacki z `CRITICAL_STACKS`
- `warning` — tylko e-mail; domyślnie dla nowo wykrytych aplikacji
- `info` — e-mail raz na dobę (deploy, logowania, nowe usługi)
- `none` — tylko watchdog (nie jest awarią)
