# Configuration Guide - VPS Monitoring Stack

## Przegląd konfiguracji

System monitoringu składa się z kilku komponentów, każdy z własną konfiguracją. Wszystkie pliki konfiguracyjne znajdują się w katalogu `config/`.

## Prometheus Configuration

### Plik: `config/prometheus/prometheus.yml`

#### Główne ustawienia

```yaml
global:
  scrape_interval: 30s      # Interwał zbierania metryk
  evaluation_interval: 15s  # Interwał ewaluacji alertów
```

#### Scrape Configs

**Static Configs:**
- `prometheus` - self-monitoring
- `node-exporter` - metryki systemowe
- `cadvisor` - metryki kontenerów

**Docker Swarm Service Discovery:**
- Automatyczne wykrywanie kontenerów z label `prometheus.io/scrape=true`
- Relabeling rules dla metadanych kontenerów

#### Retention

Retention jest konfigurowany przez zmienną środowiskową `PROMETHEUS_RETENTION`:
- Domyślnie: `720h` (30 dni)
- Format: `{number}h` (godziny) lub `{number}d` (dni)

### Dodanie custom scrape targets

Edytuj `config/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'custom-service'
    static_configs:
      - targets: ['custom-service:9090']
    metrics_path: '/metrics'
```

## Loki Configuration

### Plik: `config/loki/loki-config.yaml`

#### Główne ustawienia

```yaml
server:
  http_listen_port: 3100
  grpc_listen_port: 9096
  log_level: info
```

#### Storage

Loki używa filesystem storage:
- Chunks: `/loki/chunks`
- Index: `/loki/boltdb-shipper-active`

#### Retention

Retention jest konfigurowany przez zmienną `LOKI_RETENTION_DAYS`:
- Domyślnie: `720h` (30 dni)
- Format: `{number}h` (godziny)

#### Limits

```yaml
limits_config:
  retention_period: 720h
  ingestion_rate_mb: 16
  ingestion_burst_size_mb: 32
  max_query_parallelism: 32
  max_line_size: 256KB
```

## Promtail Configuration

### Plik: `config/promtail/promtail-config.yaml`

#### Scrape Configs

**Docker Containers:**
- Automatyczne wykrywanie kontenerów Docker
- Parsowanie logów JSON
- Labeling kontenerów

**System Logs:**
- Opcjonalne zbieranie logów systemowych z `/var/log`

#### Pipeline Stages

Promtail używa pipeline stages do przetwarzania logów:
1. **JSON parsing** - parsowanie logów JSON
2. **Timestamp extraction** - wyciąganie timestampów
3. **Label extraction** - wyciąganie labeli z logów
4. **Output** - formatowanie wyjścia

### Dodanie custom log sources

```yaml
scrape_configs:
  - job_name: 'custom-logs'
    static_configs:
      - targets:
          - localhost
        labels:
          job: custom
          __path__: /var/log/custom/*.log
```

## Grafana Configuration

### Datasources

Plik: `config/grafana/provisioning/datasources/datasources.yml`

Auto-konfiguracja datasources:
- **Prometheus**: `http://prometheus:9090`
- **Loki**: `http://loki:3100`

### Dashboards Provisioning

Plik: `config/grafana/provisioning/dashboards/dashboards.yml`

Auto-ładowanie dashboardów z:
- `/var/lib/grafana/dashboards/default` - preloadowane dashboardy
- `/var/lib/grafana/dashboards/templates` - template dashboardów

### Environment Variables

```bash
GF_SECURITY_ADMIN_PASSWORD    # Hasło admin
GF_USERS_ALLOW_SIGN_UP        # Czy pozwolić na rejestrację
GF_AUTH_ANONYMOUS_ENABLED     # Czy włączyć anonimowy dostęp
GF_SERVER_ROOT_URL            # URL Grafana
```

## Dashboard Automation

### Konfiguracja

Zmienne środowiskowe w `docker-compose.yml`:

```yaml
environment:
  - GRAFANA_URL=http://grafana:3000
  - GRAFANA_ADMIN_USER=admin
  - GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
  - PROMETHEUS_URL=http://prometheus:9090
  - CHECK_INTERVAL=60  # sekundy
```

### Jak działa

1. **Discovery**: Co `CHECK_INTERVAL` sekund, sprawdza Prometheus API (`/api/v1/targets`)
2. **Filtering**: Filtruje aktywne targets z labelami `app.name` i `app.type`
3. **Template Selection**: Wybiera template na podstawie `app.type`:
   - `wordpress` → `wordpress.json`
   - `database` → `database.json`
   - inne → `generic-app.json`
4. **Dashboard Creation**: Tworzy dashboard przez Grafana API

### Template Dashboardów

#### WordPress Template

Plik: `config/grafana/provisioning/dashboards/templates/wordpress.json`

Metryki:
- CPU Usage
- Memory Usage
- Network I/O
- Disk I/O

#### Generic App Template

Plik: `config/grafana/provisioning/dashboards/templates/generic-app.json`

Metryki:
- CPU Usage
- Memory Usage
- Network Receive/Transmit

#### Database Template

Plik: `config/grafana/provisioning/dashboards/templates/database.json`

Metryki:
- CPU Usage
- Memory Usage
- Disk I/O Read/Write

### Dodanie nowego template

1. Utwórz plik JSON w `config/grafana/provisioning/dashboards/templates/`
2. Użyj zmiennych template:
   - `{{ app_name }}`
   - `{{ app_type }}`
   - `{{ job }}`
   - `{{ container_name }}`
   - `{{ instance }}`
3. Zaktualizuj `scripts/dashboard-automation.py` w metodzie `get_template_for_app_type()`

## Uptime Kuma

### Konfiguracja

Uptime Kuma nie wymaga dodatkowej konfiguracji. Przy pierwszym uruchomieniu:
1. Otwórz `https://<MONITORING_HOST>/uptime-kuma`
2. Utwórz konto administratora
3. Dodaj monitorowane serwisy

### Backup

Dane są przechowywane w volume `uptime_kuma_data` i są backupowane przez Duplicati.

## Duplicati

### Konfiguracja backupów

1. Otwórz `https://<MONITORING_HOST>/duplicati`
2. Utwórz nowy backup job
3. Wybierz źródła z `/source/`:
   - `/source/prometheus` → Prometheus data
   - `/source/grafana` → Grafana data
   - `/source/loki` → Loki data
   - `/source/uptime-kuma` → Uptime Kuma data

### Destination

Duplicati obsługuje różne destination:
- S3 (AWS, MinIO, etc.)
- FTP/SFTP
- Google Drive
- Dropbox
- Azure Blob Storage
- Local filesystem

## Traefik Integration

### Labels

Wszystkie serwisy używają labeli Traefik dla routing:

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.services.<service>.loadbalancer.server.port=<port>"
  - "traefik.http.routers.<service>.rule=Host(`<HOST>`) && PathPrefix(`/<path>`)"
  - "traefik.http.routers.<service>.entrypoints=websecure"
  - "traefik.http.routers.<service>.middlewares=<service>-stripprefix"
  - "traefik.http.middlewares.<service>-stripprefix.stripprefix.prefixes=/<path>"
```

### Routing Paths

- `/prometheus` → Prometheus (port 9090)
- `/grafana` → Grafana (port 3000)
- `/loki` → Loki API (port 3100)
- `/uptime-kuma` → Uptime Kuma (port 3001)
- `/duplicati` → Duplicati (port 8200)

### Traefik Metrics Configuration

Monitoring stack automatycznie scrapuje metryki Traefik, jeśli są włączone.

**Wymagane w konfiguracji Traefik:**

Dodaj do `traefik.yml` lub dynamic config:

```yaml
metrics:
  prometheus:
    entryPoint: traefik  # entrypoint dla dashboard/metrics (zwykle port 8080)
    addEntryPointsLabels: true
    addServicesLabels: true
    addRoutersLabels: true
```

**Lub przez environment variables:**

```yaml
environment:
  - TRAEFIK_METRICS_PROMETHEUS_ENTRYPOINT=traefik
  - TRAEFIK_METRICS_PROMETHEUS_ADDENTRYPOINTSLABELS=true
  - TRAEFIK_METRICS_PROMETHEUS_ADDSERVICESLABELS=true
  - TRAEFIK_METRICS_PROMETHEUS_ADDROUTERSLABELS=true
```

**Sprawdzenie:**

Metryki powinny być dostępne na `http://traefik:8080/metrics` (wewnątrz sieci).

**Prometheus scrape config:**

Stack automatycznie scrapuje Traefik na `traefik:8080/metrics` (30s interval).

**Alerty Traefik:**

- `TraefikHighRequestRate` - wysokie request rate (>100 req/sec)
- `TraefikHighResponseTime` - wysokie response time (>2s 95th percentile)
- `TraefikEntrypointDown` - endpoint metryk nie odpowiada

## Zmienne środowiskowe

### Wszystkie zmienne

| Zmienna | Opis | Domyślna wartość |
|---------|------|------------------|
| `GRAFANA_ADMIN_PASSWORD` | Hasło admin Grafana | `admin` |
| `GRAFANA_ADMIN_USER` | Użytkownik admin Grafana | `admin` |
| `MONITORING_HOST` | IP hosta dla Traefik routing | `57.129.41.248` |
| `PROMETHEUS_RETENTION` | Retention danych Prometheus | `720h` |
| `LOKI_RETENTION_DAYS` | Retention logów Loki | `720` (hours) |
| `GRAFANA_URL` | URL Grafana API | `http://grafana:3000` |
| `PROMETHEUS_URL` | URL Prometheus API | `http://prometheus:9090` |
| `CHECK_INTERVAL` | Interwał sprawdzania nowych kontenerów | `60` (seconds) |
| `TELEGRAM_BOT_TOKEN` | Token bota Telegram (z @BotFather) | - |
| `TELEGRAM_CHAT_ID` | ID czatu/channelu dla powiadomień | - |

## Zaawansowana konfiguracja

### Custom Prometheus Rules

Dodaj pliki z regułami do `config/prometheus/` i zmontuj w `docker-compose.yml`:

```yaml
volumes:
  - ./config/prometheus/rules:/etc/prometheus/rules:ro
```

Zaktualizuj `prometheus.yml`:

```yaml
rule_files:
  - "rules/*.yml"
```

### Custom Grafana Plugins

Dodaj plugin do `GF_INSTALL_PLUGINS`:

```yaml
environment:
  - GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-piechart-panel
```

### Loki Retention Policies

Można skonfigurować różne retention policies dla różnych labeli:

```yaml
limits_config:
  retention_period: 720h
  per_stream_rate_limit: 3MB
  per_stream_rate_limit_burst: 15MB
```

## Performance Tuning

### Prometheus

```yaml
# Zwiększ retention dla większej ilości danych
storage:
  tsdb:
    retention: 90d  # 90 dni
```

### Loki

```yaml
# Zwiększ limits dla większego loadu
limits_config:
  ingestion_rate_mb: 32
  ingestion_burst_size_mb: 64
  max_query_parallelism: 64
```

### Grafana

```yaml
# Zwiększ timeout dla dużych zapytań
[server]
query_timeout = 300s
```

## Security

### Zmiana domyślnych haseł

**Wymagane:**
1. Zmień `GRAFANA_ADMIN_PASSWORD` w `.env`
2. Zmień hasło w Uptime Kuma przez interfejs webowy
3. Skonfiguruj backup w Duplicati z bezpiecznymi credentials

### Network Security

Wszystkie serwisy są w sieci `monitoring` (overlay), która jest izolowana. Tylko Traefik ma dostęp przez `traefik-public`.

### API Security

- Grafana API wymaga autoryzacji (admin credentials)
- Prometheus API jest dostępny tylko w sieci `monitoring`
- Loki API jest dostępny tylko w sieci `monitoring`

