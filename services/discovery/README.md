# discovery

Serce automatycznego monitoringu. Czyta Docker Swarm API przez
`unix:///var/run/docker.sock` (**wyłącznie zapytania GET** — serwis nie ma
możliwości zmiany czegokolwiek na hoście), parsuje trasy Traefika z labeli usług,
buduje cele dla Prometheus HTTP SD (blackbox), wykonuje własne sondy HTTP/TLS
i wystawia metryki Prometheusa oraz zagregowany JSON dla panelu.

Odświeżanie odbywa się w wątku w tle co `REFRESH_SECONDS` (domyślnie 30 s).

## Endpointy (domyślnie port 8080)

| Endpoint | Opis |
| --- | --- |
| `GET /health` | `{"status":"ok","up":true,...}`; `up` = czy ostatnie odświeżenie się udało |
| `GET /sd/http.json` | Prometheus HTTP SD dla blackboxa — jeden wpis na URL |
| `GET /metrics` | Ekspozycja Prometheusa (`text/plain; version=0.0.4`) |
| `GET /status/api.json` | Zagregowany stan dla panelu (host, checks, stacks, certs, backup, alerts, security, tools) |
| `GET /` | Lista endpointów |

Obsługiwane są tylko `GET` i `HEAD`; pozostałe metody zwracają 405.
Każde połączenie obsługiwane jest w osobnym wątku, a `SIGTERM` zamyka serwer czysto.

### Format HTTP SD

```json
[{"targets":["https://app.ventiplan.pl/health"],
  "labels":{"stack":"ventiplan-prod","service":"api","app":"ventiplan",
            "module":"http_2xx","__param_module":"http_2xx",
            "severity":"critical","source":"discovery"}}]
```

`module` i `__param_module` mają zawsze identyczną wartość: pierwszy jest czytelny,
drugi jest tym, którego Prometheus używa jako parametru sondy.

## Metryki

`swarm_service_desired_replicas`, `swarm_service_running_replicas`,
`swarm_service_tasks`, `swarm_service_failed_tasks_1h`, `swarm_service_info`,
`swarm_service_updated_at`, `swarm_container_cpu_percent`,
`swarm_container_memory_bytes`, `swarm_container_memory_limit_bytes`,
`swarm_container_health`,
`swarm_container_network_receive_bytes_total`, `swarm_container_network_transmit_bytes_total`
(liczniki narastające — w zapytaniach liczymy z nich `rate()`, więc wykresy pokazują B/s),
`swarm_container_block_read_bytes_total`, `swarm_container_block_write_bytes_total`,
`discovery_probe_success`, `discovery_probe_latency_seconds`,
`discovery_cert_days_left`, `discovery_http_targets`, `discovery_stacks`,
`discovery_services`, `discovery_up`, `discovery_last_refresh_timestamp_seconds`,
`discovery_new_services_total`, `docker_images_reclaimable_bytes`,
`docker_volumes_reclaimable_bytes`, `docker_containers`,
`docker_containers_running`.

### Konwencja nazw

Sufiks `_total` należy wyłącznie do liczników (`discovery_new_services_total`).
Liczba kontenerów to gauge `docker_containers` — nazwa `docker_containers_total`
została zmieniona, bo `promtool check metrics` słusznie zgłaszał
`non-counter metrics should not have "_total" suffix`. Tę samą regułę pilnuje
test `tests/test_discovery.py::MetricLintTests::test_total_suffix_only_for_counters`.

## Etykiety sterujące (na usłudze Docker)

| Label | Znaczenie |
| --- | --- |
| `monitoring.io/skip=true` | pomiń usługę |
| `monitoring.io/probe=<URL>` | użyj dokładnie tego adresu (zamiast budowanego z reguły) |
| `monitoring.io/health-path=/x` | zamiast ścieżki z reguły Traefika użyj `/x` |
| `monitoring.io/severity=critical\|warning\|skip` | priorytet (nadpisuje `CRITICAL_STACKS`/`WARN_STACKS`) |
| `monitoring.io/module=<nazwa>` | moduł blackboxa (nadpisuje mapowanie z `expect`) |
| `monitoring.io/name=<nazwa>` | nazwa usługi w SD i panelu |
| `monitoring.io/expect=<kod>` | `200` → `http_2xx`, `401` → `http_expect_auth`, inny → `http_alive` |
| `monitoring.io/app=<nazwa>` | etykieta `app` w SD (domyślnie pierwszy człon nazwy stacka) |

Reguły Traefika czytane są z labeli `traefik.http.routers.<router>.rule`
(obsługiwane są backticki, apostrofy i cudzysłowy). Usługi z `traefik.enable=false`
są pomijane. Przy wielu routerach na usługę powstaje wiele celów, ale identyczne
adresy są deduplikowane.

## Zmienne środowiskowe

| Zmienna | Domyślnie | Opis |
| --- | --- | --- |
| `DOCKER_HOST` | `/var/run/docker.sock` | wyłącznie gniazdo unix (`unix:///...`); `tcp://` to błąd konfiguracji |
| `REFRESH_SECONDS` | `30` | odstęp odświeżania |
| `SKIP_STACKS` | – | lista stacków po przecinku do pominięcia |
| `SKIP_SERVICES` | – | lista usług po przecinku do pominięcia (pełna nazwa lub część po `_`) |
| `CRITICAL_STACKS` | – | stacki domyślnie `critical` |
| `WARN_STACKS` | – | stacki domyślnie `warning` |
| `DEFAULT_PROBE_PATH` | puste | ścieżka doklejana, gdy reguła nie ma `PathPrefix`; puste = sonda na sam host |
| `BLACKBOX_MODULE` | `http_2xx` | domyślny moduł blackboxa |
| `PROBE_TIMEOUT_SECONDS` | `5` | timeout własnych sond HTTP i odczytu certyfikatów |
| `PROMETHEUS_URL` | `http://prometheus:9090` | źródło danych o hoście |
| `ALERTMANAGER_URL` | `http://alertmanager:9093` | źródło aktywnych alertów |
| `HEALTH_PING_URL` | `http://health-ping:8080` | źródło sekcji `backup` |
| `MONITORING_DOMAIN` | `monitoring.subscribeit.pl` | domena, na której sondowane są narzędzia wewnętrzne |
| `SECURITY_JSON_URL` | puste | opcjonalne źródło sekcji `security` |
| `PORT` | `8080` | port HTTP |

## Zachowanie przy braku zależności

Gdy Docker API nie odpowiada (np. gniazdo niedostępne dla UID 10001 — dostęp
rozwiązuje `group_add` w compose), `discovery_up` = 0, `/health` zwraca
`{"status":"degraded","up":false}`, a serwis dalej działa i serwuje ostatnią znaną
migawkę oraz kompletny `/status/api.json` (HTTP 200). Serwis nie wymaga uprawnień
roota i nie podnosi ich samodzielnie. Brak Prometheusa → sekcja `host` wypełniona zerami,
`overall` co najmniej `warning`. Brak Alertmanagera → pusta lista `alerts`.
Brak `health-ping` → sekcja `backup` w stanie `unknown`.

## Ustalenia i odstępstwa

- **Usługi w trybie `Global`** (np. `portainer_agent`, `promtail`, `node-exporter`)
  nie mają zadeklarowanej liczby replik, więc `desired` = liczba aktualnie
  działających zadań. Dzięki temu panel i alerty nie pokazują fałszywego `0/0`.
  To samo dotyczy trybów `*Job` i jest używane w `stacks[].services[].desired`
  oraz w `replicas_text`.
- **Sonda HTTP wykonywana jest raz na cykl na unikalny URL** (deduplikacja po
  adresie, nie po routerze) i tylko dla celów, których `severity` nie jest `skip`.
- **TLS**: sonda używa `ssl` z `check_hostname=False` i `verify_mode=CERT_NONE`,
  ale handshake musi się udać — dzięku temu „cert wygasł" i „nie ma TLS" to dwie
  różne sytuacje. Certyfikaty czytane są przez `ssl.get_server_certificate` +
  `ssl.PEM_cert_to_DER_cert` i własny mini-parser ASN.1 (bez bibliotek
  zewnętrznych), z cache 1 h (błąd cache'owany 5 min).
- `restarts_1h` w `stacks[].services[]` to liczba zadań, które w ostatniej
  godzinie nie osiągnęły stanu `running` przy `DesiredState=running`
  (ta sama wartość co `swarm_service_failed_tasks_1h`).
- `BuildCache` z `/system/df` jest odczytywany, ale nieeksponowany — specyfikacja
  nie podaje dla niego nazwy metryki.
- `docker_images_reclaimable_bytes` liczy sumę `Size` obrazów nieużywanych
  (`Images[].Containers == 0`); gdy Docker nie zwraca tej flagi, używany jest
  `LayersSize`.
- Stan narzędzia wewnętrznego w `tools[]` pochodzi z sondy
  `<MONITORING_DOMAIN><url>`; narzędzia zewnętrzne mają zawsze `state: "unknown"`.
- `checks[]` korzysta z wyników sond z ostatniego cyklu odświeżania (te same dane,
  które zasilają `discovery_probe_*`), więc `/status/api.json` nie generuje ruchu.
- Zapytania do Prometheusa są cache'owane na 10 s, żeby panel mógł odpytywać
  `/status/api.json` bez obciążania Prometheusa.

## Uruchomienie

```bash
docker build -t monitoring/discovery services/discovery
docker run --rm -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -e CRITICAL_STACKS=ventiplan-prod -e WARN_STACKS=monitoring \
  monitoring/discovery
```

Kontener działa jako UID 10001 i nie zapisuje niczego poza `/tmp`.
