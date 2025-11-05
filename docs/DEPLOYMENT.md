# Deployment Guide - VPS Monitoring Stack

## Wymagania wstępne

### Infrastruktura

- Docker Swarm zainicjalizowany (min. 1 manager node)
- Traefik z siecią `traefik-public` (external network)
- Minimum 2GB RAM dostępnej
- Minimum 10GB wolnego miejsca na dysku dla volumes

### Porty

Następujące porty muszą być dostępne:
- `3000` - Grafana (opcjonalnie, jeśli dostęp przez Traefik)
- `3001` - Uptime Kuma (opcjonalnie)
- `3100` - Loki (opcjonalnie)
- `8200` - Duplicati (opcjonalnie)
- `9090` - Prometheus (opcjonalnie)
- `9100` - Node Exporter
- `8081` - cAdvisor

## Instalacja krok po kroku

### 1. Przygotowanie środowiska

```bash
# Sklonuj repozytorium
git clone <repository-url>
cd vps-monitoring

# Template zmiennych środowiskowych
# Zobacz env.portainer.example dla listy wszystkich zmiennych
```

### 2. Konfiguracja zmiennych środowiskowych

#### Opcja A: W Portainer (Rekomendowane)

1. **Otwórz Portainer** → **Stacks**
2. **Wybierz stack** `monitoring` (lub utwórz nowy)
3. **Kliknij "Editor"** (lub "Update the stack")
4. **W sekcji "Environment variables"** dodaj następujące zmienne:

```env
# Grafana Configuration
GRAFANA_ADMIN_PASSWORD=twoje_bezpieczne_haslo_grafana
GRAFANA_ADMIN_USER=admin

# Monitoring Host Configuration
MONITORING_HOST=57.129.41.248

# Prometheus Configuration
PROMETHEUS_RETENTION=720h

# Loki Configuration
LOKI_RETENTION_DAYS=720

# Dashboard Automation Configuration
GRAFANA_URL=http://grafana:3000
PROMETHEUS_URL=http://prometheus:9090
CHECK_INTERVAL=60

# Telegram Alerting Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

**Jak dodać zmienną w Portainer:**
- Kliknij **"Add environment variable"**
- **Name**: `GRAFANA_ADMIN_PASSWORD`
- **Value**: `twoje_haslo`
- Kliknij **"Add"**
- Powtórz dla wszystkich zmiennych

**Template zmiennych:** Zobacz `env.portainer.example` w repozytorium - gotowy template z wszystkimi zmiennymi i komentarzami.

#### Opcja B: Lokalny plik .env

Jeśli używasz `docker stack deploy` z linii poleceń:

```bash
nano .env
```

Ustaw następujące wartości:

```env
# Grafana Configuration
GRAFANA_ADMIN_PASSWORD=<secure-password>
GRAFANA_ADMIN_USER=admin

# Monitoring Host Configuration
MONITORING_HOST=<your-server-ip>

# Prometheus Configuration
PROMETHEUS_RETENTION=720h  # 30 days

# Loki Configuration
LOKI_RETENTION_DAYS=720  # 30 days

# Dashboard Automation (opcjonalne)
CHECK_INTERVAL=60  # seconds

# Telegram Alerting (opcjonalne, ale zalecane)
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
```

### 3. Weryfikacja sieci Traefik

Upewnij się, że sieć `traefik-public` istnieje:

```bash
docker network ls | grep traefik-public
```

Jeśli nie istnieje, utwórz ją:

```bash
docker network create --driver overlay traefik-public
```

### 4. Wdrożenie stacku

```bash
# Wdróż stack
docker stack deploy -c docker-compose.yml monitoring

# Sprawdź status
docker stack services monitoring
```

### 5. Weryfikacja wdrożenia

Sprawdź czy wszystkie serwisy działają:

```bash
# Lista serwisów
docker service ls | grep monitoring

# Sprawdź logi
docker service logs monitoring_prometheus
docker service logs monitoring_grafana
docker service logs monitoring_dashboard-automation
```

### 6. Dostęp do serwisów

#### Przez Traefik (HTTPS):

- Grafana: `https://<MONITORING_HOST>/grafana`
- Prometheus: `https://<MONITORING_HOST>/prometheus`
- Uptime Kuma: `https://<MONITORING_HOST>/uptime-kuma`
- Duplicati: `https://<MONITORING_HOST>/duplicati`

#### Bezpośredni dostęp:

- Grafana: `http://<MONITORING_HOST>:3000` (domyślnie: admin/admin)
- Prometheus: `http://<MONITORING_HOST>:9090`
- Uptime Kuma: `http://<MONITORING_HOST>:3001` (pierwsze uruchomienie - utwórz konto)

## Konfiguracja kontenerów do monitorowania

### Dodanie labeli do istniejącego serwisu

Aby automatycznie monitorować kontener, dodaj labels do serwisu w Docker Swarm:

```yaml
# W docker-compose.yml lub Portainer
services:
  your-service:
    # ... konfiguracja serwisu
    labels:
      - "prometheus.io/scrape=true"
      - "prometheus.io/port=9090"          # Port z metrykami
      - "prometheus.io/path=/metrics"       # Ścieżka do metryk
      - "prometheus.io/job=your-service"    # Nazwa job w Prometheus
      - "app.name=your-app-name"            # Nazwa aplikacji (dla dashboardów)
      - "app.type=wordpress"                # Typ aplikacji
```

### Przykład: WordPress Production

```yaml
services:
  wordpress:
    # ... konfiguracja
    labels:
      - "prometheus.io/scrape=true"
      - "prometheus.io/port=9090"
      - "app.name=wordpress-production"
      - "app.type=wordpress"
    networks:
      - traefik-public  # Aby Prometheus mógł się połączyć
```

### Automatyczne tworzenie dashboardów

Po dodaniu labeli `app.name` i `app.type`, serwis `dashboard-automation` automatycznie:

1. Wykryje nowy kontener w Prometheus (co 60 sekund)
2. Sprawdzi czy dashboard już istnieje
3. Utworzy nowy dashboard używając odpowiedniego template:
   - `wordpress` → template WordPress
   - `database` → template Database
   - `api`, `generic` → template Generic App

## Aktualizacja stacku

```bash
# Zatrzymaj stack (opcjonalnie, jeśli potrzebujesz zero-downtime)
# docker stack rm monitoring

# Wdróż zaktualizowaną konfigurację
docker stack deploy -c docker-compose.yml monitoring

# Sprawdź aktualizacje
docker service ps monitoring_prometheus
```

## Backup danych

### Automatyczny backup przez Duplicati

1. Otwórz Duplicati: `https://<MONITORING_HOST>/duplicati`
2. Utwórz nowy backup job
3. Wybierz źródła:
   - `/source/prometheus` → Prometheus data
   - `/source/grafana` → Grafana data
   - `/source/loki` → Loki data
   - `/source/uptime-kuma` → Uptime Kuma data
4. Skonfiguruj destination (S3, FTP, SFTP, etc.)
5. Ustaw harmonogram

### Ręczny backup volumes

```bash
# Backup Prometheus
docker run --rm -v monitoring_prometheus_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/prometheus-backup.tar.gz /data

# Backup Grafana
docker run --rm -v monitoring_grafana_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/grafana-backup.tar.gz /data

# Backup Loki
docker run --rm -v monitoring_loki_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/loki-backup.tar.gz /data
```

### Restore z backupu

```bash
# Restore Prometheus
docker run --rm -v monitoring_prometheus_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/prometheus-backup.tar.gz -C /

# Restore Grafana
docker run --rm -v monitoring_grafana_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/grafana-backup.tar.gz -C /
```

## Troubleshooting

### Serwis nie startuje

```bash
# Sprawdź logi
docker service logs monitoring_<service-name>

# Sprawdź status
docker service ps monitoring_<service-name>

# Sprawdź konfigurację
docker service inspect monitoring_<service-name>
```

### Prometheus nie wykrywa kontenerów

1. Sprawdź czy kontener ma label `prometheus.io/scrape=true`
2. Sprawdź czy kontener jest w sieci dostępnej dla Prometheus
3. Sprawdź czy port jest poprawny
4. Sprawdź logi Prometheus: `docker service logs monitoring_prometheus`

### Grafana nie pokazuje dashboardów

1. Sprawdź czy datasources są poprawnie skonfigurowane
2. Sprawdź logi dashboard-automation: `docker service logs monitoring_dashboard-automation`
3. Sprawdź czy Prometheus targets są aktywne
4. Sprawdź czy kontenery mają labeli `app.name` i `app.type`

### Problemy z Traefik routing

1. Sprawdź czy sieć `traefik-public` istnieje i jest external
2. Sprawdź logi Traefik
3. Sprawdź czy labels są poprawnie ustawione
4. Sprawdź czy port jest poprawny w labelach

## Monitoring i alerty

### Sprawdzenie metryk

```bash
# Prometheus targets
curl http://localhost:9090/api/v1/targets | jq

# Prometheus metrics
curl http://localhost:9090/api/v1/query?query=up

# Grafana health
curl http://localhost:3000/api/health
```

### Konfiguracja alertów

Alerty można skonfigurować w Grafana:
1. Otwórz Grafana
2. Przejdź do Alerting → Alert Rules
3. Utwórz nową regułę
4. Użyj PromQL queries do definiowania alertów

Przykład alertu dla wysokiego użycia CPU:
```promql
rate(container_cpu_usage_seconds_total[5m]) * 100 > 80
```

## Skalowanie

### Zwiększenie liczby replik

```bash
# Zwiększ repliki Grafana (niezalecane, tylko dla HA)
docker service scale monitoring_grafana=2

# Zwiększ repliki Prometheus (niezalecane, tylko dla HA)
docker service scale monitoring_prometheus=2
```

**Uwaga:** Większość serwisów powinna mieć tylko 1 replikę, ponieważ używają persistent volumes.

## Usunięcie stacku

```bash
# Zatrzymaj i usuń stack
docker stack rm monitoring

# Usuń volumes (UWAGA: usuwa wszystkie dane!)
docker volume rm monitoring_prometheus_data
docker volume rm monitoring_grafana_data
docker volume rm monitoring_loki_data
docker volume rm monitoring_uptime_kuma_data
docker volume rm monitoring_duplicati_data
```

