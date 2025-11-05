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

### 4. Tworzenie Docker Swarm Configs

**⚠️ WAŻNE:** Przed wdrożeniem stacku musisz utworzyć Docker Swarm Configs. Stack używa `external: true` configs zamiast bind mounts, aby działać w Portainer z Git repository.

#### Opcja A: Przez Portainer UI (Zalecane)

1. **W Portainer** → **Configs** → **Add config**
2. Dla każdego pliku konfiguracyjnego:
   - **Name**: (patrz lista poniżej)
   - **Content**: Skopiuj zawartość pliku z repozytorium
   - Kliknij **Create the config**

**Lista configs do utworzenia:**

| Config Name | Plik źródłowy |
|------------|---------------|
| `prometheus_config` | `config/prometheus/prometheus.yml` |
| `prometheus_alerts_system` | `config/prometheus/alerts/system.yml` |
| `prometheus_alerts_http` | `config/prometheus/alerts/http.yml` |
| `prometheus_alerts_monitoring` | `config/prometheus/alerts/monitoring.yml` |
| `prometheus_alerts_prometheus` | `config/prometheus/alerts/prometheus.yml` |
| `loki_config` | `config/loki/loki-config.yaml` |
| `promtail_config` | `config/promtail/promtail-config.yaml` |
| `alertmanager_config` | `config/alertmanager/alertmanager.yml` |
| `blackbox_config` | `config/blackbox/blackbox.yml` |
| `grafana_datasources` | `config/grafana/provisioning/datasources/datasources.yml` |
| `grafana_dashboards` | `config/grafana/provisioning/dashboards/dashboards.yml` |
| `telegram_webhook_script` | `scripts/telegram-webhook.py` |
| `telegram_webhook_requirements` | `scripts/requirements.txt` |
| `dashboard_automation_script` | `scripts/dashboard-automation.py` |

**Uwaga:** Nazwy configs muszą być dokładnie takie same jak w tabeli powyżej!

#### Opcja B: Przez CLI (szybsze)

Jeśli masz dostęp SSH do VPS:

```bash
# Sklonuj repozytorium (jeśli jeszcze nie masz)
git clone <repository-url>
cd vps-monitoring

# Uruchom skrypt tworzenia configs
./scripts/create-configs.sh create

# Sprawdź czy configs zostały utworzone
./scripts/create-configs.sh list
```

**Aktualizacja configs po zmianie plików:**

```bash
# Zaktualizuj pliki w repozytorium
git pull

# Zaktualizuj configs (skrypt automatycznie usuwa i tworzy na nowo)
./scripts/create-configs.sh create
```

#### Opcja C: Ręcznie przez Docker CLI

```bash
# Przykład: tworzenie prometheus_config
docker config create prometheus_config config/prometheus/prometheus.yml

# Powtórz dla wszystkich plików z listy powyżej
```

### 5. Przygotowanie katalogu templates (opcjonalnie)

**Uwaga:** Grafana templates directory wymaga bind mount (katalog, nie pojedynczy plik). 

**Opcja 1: Użyj standardowej ścieżki (jeśli masz dostęp SSH):**

```bash
# Na VPS, utwórz katalog i skopiuj templates
sudo mkdir -p /opt/vps-monitoring/config/grafana/provisioning/dashboards/templates
sudo cp -r config/grafana/provisioning/dashboards/templates/* /opt/vps-monitoring/config/grafana/provisioning/dashboards/templates/
```

**Opcja 2: Zmień ścieżkę w docker-compose.yml:**

Jeśli Portainer klonuje repo do innej lokalizacji, zmień w `docker-compose.yml`:
- Grafana service: zmień `/opt/vps-monitoring/...` na właściwą ścieżkę
- Dashboard-automation service: zmień `/opt/vps-monitoring/...` na właściwą ścieżkę

**Opcja 3: Pomiń templates (dashboard-automation będzie działać, ale bez preloaded templates):**

Możesz usunąć bind mount dla templates - dashboard-automation będzie tworzyć dashboardy bez preloaded templates.

### 6. Wdrożenie stacku

**W Portainer:**
1. **Stacks** → **Add stack**
2. **Name**: `monitoring`
3. **Type**: `Docker Swarm`
4. **Build method**: `Repository` (Git)
5. **Repository URL**: Twój GitHub repository URL
6. **Repository reference**: `main`
7. **Compose path**: `docker-compose.yml`
8. Dodaj zmienne środowiskowe (patrz Krok 2)
9. Kliknij **Deploy the stack**

**Lub przez CLI:**
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

### Docker Image Pulling

**TAK - Portainer automatycznie ściąga obrazy Docker przy deployu/aktualizacji stacku.**

**Jak to działa:**

1. **Przy pierwszym deployu:**
   - Portainer analizuje `docker-compose.yml`
   - Dla każdego serwisu sprawdza `image:` 
   - Automatycznie wykonuje `docker pull <image>` dla każdego obrazu
   - Tworzy kontenery z pobranymi obrazami

2. **Przy aktualizacji stacku (webhook lub Pull and redeploy):**
   - Portainer sprawdza czy obrazy się zmieniły
   - Jeśli `image:` tag się zmienił (np. `latest` → nowszy build), ściąga nowy obraz
   - Aktualizuje kontenery z nowymi obrazami

**Obrazy w tym stacku (wszystkie publiczne):**

Wszystkie obrazy używane w `docker-compose.yml` są z **publicznych rejestrów**:
- Docker Hub: `prom/prometheus:latest`, `grafana/grafana:latest`, `grafana/loki:latest`, etc.
- Google Container Registry: `gcr.io/cadvisor/cadvisor:v0.47.0`
- LinuxServer.io: `lscr.io/linuxserver/duplicati:latest`
- Python official: `python:3.11-slim`

**✅ Nie wymagają autoryzacji - Portainer automatycznie je ściąga.**

**Jeśli używasz własnych obrazów z GitHub Container Registry (ghcr.io):**

**Publiczne obrazy ghcr.io:**
- ✅ Działają automatycznie - Portainer ściąga je bez dodatkowej konfiguracji
- Format: `ghcr.io/username/repo:tag`

**Prywatne obrazy ghcr.io:**
- ⚠️ **Wymagają Registry authentication** w Portainer
- Konfiguracja:

1. **W Portainer** → **Registries** → **Add registry**
2. Wybierz **Custom** (dla ghcr.io)
3. **Name**: `GitHub Container Registry` (lub dowolna nazwa)
4. **Registry URL**: `https://ghcr.io`
5. **Authentication**:
   - **Username**: Twój GitHub username
   - **Password**: GitHub Personal Access Token (PAT)
6. Kliknij **Create registry**

**GitHub Personal Access Token:**
1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. **Generate new token (classic)**
3. **Note**: `Portainer ghcr.io access`
4. **Expiration**: Wybierz okres (np. 90 dni lub No expiration)
5. **Scopes**: Zaznacz `read:packages` (minimum)
6. **Generate token**
7. **Skopiuj token** - użyj jako password w Portainer registry

**Po skonfigurowaniu:**
- Portainer automatycznie użyje tego registry przy pull obrazów z `ghcr.io`
- Obrazy są cache'owane lokalnie - nie są ściągane przy każdym deployu jeśli nie zmienił się tag
- Portainer automatycznie wykrywa nowsze wersje jeśli używasz tagów jak `latest` lub `production`

**Przykład użycia własnego obrazu:**

Jeśli masz własny obraz w `docker-compose.yml`:
```yaml
services:
  my-service:
    image: ghcr.io/your-username/your-repo:production
    # ... reszta konfiguracji
```

I obraz jest **prywatny**:
- Skonfiguruj Registry w Portainer (jak wyżej)
- Portainer automatycznie użyje credentials przy pull

Jeśli obraz jest **publiczny**:
- Nie wymaga konfiguracji - działa automatycznie

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

