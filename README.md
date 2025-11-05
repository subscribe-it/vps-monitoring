# VPS Monitoring Stack

Kompletny system monitoringu dla infrastruktury VPS oparty na Docker Swarm. Zawiera Prometheus, Grafana, Loki, Uptime Kuma, Duplicati oraz automatyczne tworzenie dashboardów dla nowych serwisów.

## 📊 Komponenty systemu

### Docker Swarm Stack

- **Node Exporter** - metryki systemowe hosta
- **cAdvisor** - metryki kontenerów Docker (global mode - jeden na każdym nodzie)
- **Prometheus** - zbieranie i przechowywanie metryk z Docker Swarm Service Discovery
- **Alertmanager** - zarządzanie alertami i powiadomieniami
- **Telegram Webhook** - serwis do wysyłania alertów przez Telegram
- **Blackbox Exporter** - monitoring HTTP/HTTPS endpoints
- **Loki** - agregacja logów z retention 30 dni
- **Promtail** - zbieranie logów z kontenerów Docker (global mode)
- **Grafana** - wizualizacja, dashboardy, auto-provisioning datasources
- **Uptime Kuma** - monitoring dostępności usług (z możliwością auto-restart)
- **Duplicati** - backup danych monitoringu (Prometheus, Grafana, Loki, Uptime Kuma)
- **Dashboard Automation** - automatyczne tworzenie dashboardów dla nowo wykrytych serwisów

### Kluczowe funkcje

- **Automatyczne wykrywanie kontenerów** - Prometheus używa Docker Swarm Service Discovery
- **Automatyczne dashboardy** - serwis dashboard-automation tworzy dashboardy dla nowych serwisów
- **Auto-provisioning** - Grafana automatycznie konfiguruje datasources i dashboardy
- **Backup** - Duplicati backupuje wszystkie dane monitoringu
- **Traefik Integration** - wszystkie serwisy dostępne przez HTTPS z path prefixes

## 🚀 Quick Start

### Wymagania

- Docker Swarm zainicjalizowany
- Traefik z siecią `traefik-public`
- Porty: 3000, 3001, 3100, 8200, 9090, 9100, 8081, 8080, 9093, 9115
- Portainer (dostęp do web UI)

## 📦 Wdrożenie w Portainer

### Krok 1: Przygotowanie repozytorium

**Opcja A: W Portainer (Rekomendowane)**

1. Otwórz Portainer → **Stacks**
2. Kliknij **Add stack**
3. Wybierz **Web editor**
4. Nazwa stacku: `monitoring`
5. Wklej zawartość pliku `docker-compose.yml` do edytora

**Opcja B: Z Git Repository**

1. Otwórz Portainer → **Stacks**
2. Kliknij **Add stack**
3. Wybierz **Git repository**
4. **Repository URL**: `https://github.com/twoje-repo/vps-monitoring.git`
5. **Repository reference**: `main` (lub branch)
6. **Compose path**: `docker-compose.yml`
7. **Auto-update**: (opcjonalnie) włącz dla automatycznych aktualizacji

### Krok 2: Konfiguracja zmiennych środowiskowych

1. W Portainer Stack Editor, przewiń do sekcji **Environment variables**
2. Kliknij **Add environment variable** dla każdej zmiennej:

#### Wymagane zmienne:

| Name | Value | Opis |
|------|-------|------|
| `GRAFANA_ADMIN_PASSWORD` | `twoje_bezpieczne_haslo` | Hasło admin Grafana (min. 8 znaków) |
| `MONITORING_HOST` | `57.129.41.248` | IP Twojego VPS (lub domena) |
| `PROMETHEUS_RETENTION` | `720h` | Retention danych Prometheus (30 dni) |
| `LOKI_RETENTION_DAYS` | `720` | Retention logów Loki (30 dni) |

#### Opcjonalne zmienne (zalecane):

| Name | Value | Opis |
|------|-------|------|
| `TELEGRAM_BOT_TOKEN` | `123456789:ABC...` | Token bota Telegram z @BotFather |
| `TELEGRAM_CHAT_ID` | `123456789` | ID czatu/channelu dla alertów |
| `GRAFANA_ADMIN_USER` | `admin` | Użytkownik admin Grafana (domyślnie: admin) |
| `CHECK_INTERVAL` | `60` | Interwał sprawdzania nowych kontenerów (sekundy) |

**Przykład dodawania zmiennej:**

1. Kliknij **Add environment variable**
2. **Name**: `GRAFANA_ADMIN_PASSWORD`
3. **Value**: `MojeSilneHaslo123!`
4. Kliknij **Add**
5. Powtórz dla wszystkich zmiennych

**Gotowy template:** Zobacz `env.portainer.example` w repozytorium - możesz skopiować wszystkie zmienne stamtąd.

### Krok 3: Weryfikacja sieci Traefik

1. W Portainer, przejdź do **Networks**
2. Sprawdź czy istnieje sieć `traefik-public`
3. Jeśli nie istnieje:
   - Kliknij **Add network**
   - **Name**: `traefik-public`
   - **Driver**: `overlay`
   - **Scope**: `swarm`
   - **Attachable**: ✓ (zaznacz)
   - Kliknij **Create**

### Krok 4: Wdrożenie stacku

1. W Portainer Stack Editor, przewiń do dołu
2. Sprawdź czy wszystkie zmienne środowiskowe są dodane
3. Kliknij **Deploy the stack**
4. Poczekaj na utworzenie wszystkich serwisów (około 1-2 minuty)

### Krok 5: Weryfikacja wdrożenia

1. W Portainer → **Stacks** → **monitoring**
2. Sprawdź status wszystkich serwisów:
   - Wszystkie powinny być w stanie **Running** (zielony)
   - Jeśli któryś jest **Pending** lub **Failed**, kliknij na niego i sprawdź logi

3. Sprawdź logi serwisów:
   - Kliknij na serwis (np. `prometheus`)
   - Kliknij **Logs**
   - Sprawdź czy nie ma błędów

4. Sprawdź status przez terminal:
```bash
docker service ls | grep monitoring
```

Oczekiwany output (12 serwisów):
```
ID             NAME                        MODE         REPLICAS   IMAGE
xxx            monitoring_alertmanager    replicated   1/1        prom/alertmanager:latest
xxx            monitoring_blackbox-exporter replicated  1/1        prom/blackbox-exporter:latest
xxx            monitoring_cadvisor         global       1/1        gcr.io/cadvisor/cadvisor:v0.47.0
xxx            monitoring_dashboard-automation replicated 1/1     python:3.11-slim
xxx            monitoring_duplicati       replicated   1/1        lscr.io/linuxserver/duplicati:latest
xxx            monitoring_grafana          replicated   1/1        grafana/grafana:latest
xxx            monitoring_loki             replicated   1/1        grafana/loki:latest
xxx            monitoring_node-exporter    global       1/1        prom/node-exporter:latest
xxx            monitoring_prometheus       replicated   1/1        prom/prometheus:latest
xxx            monitoring_promtail         global       1/1        grafana/promtail:latest
xxx            monitoring_telegram-webhook replicated   1/1        python:3.11-slim
xxx            monitoring_uptime-kuma      replicated   1/1        louislam/uptime-kuma:latest
```

### Krok 6: Konfiguracja Telegram (opcjonalnie, ale zalecane)

**A. Utworzenie bota Telegram:**

1. Otwórz Telegram i znajdź [@BotFather](https://t.me/BotFather)
2. Wyślij `/newbot`
3. Podaj nazwę bota (np. "VPS Monitoring Bot")
4. Podaj username bota (np. "vps_monitoring_bot")
5. Skopiuj **token** bota (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

**B. Uzyskanie Chat ID:**

**Dla czatu prywatnego:**
1. Napisz wiadomość do swojego bota
2. Otwórz w przeglądarce: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Zastąp `<TOKEN>` tokenem bota
3. Znajdź w odpowiedzi: `"chat":{"id":123456789}`
4. To jest Twój Chat ID

**Dla kanału/grupy:**
1. Dodaj bota do kanału/grupy
2. Uczyń bota administratorem kanału
3. Wyślij wiadomość do kanału
4. Sprawdź `getUpdates` API - znajdź ID kanału (ujemne dla kanałów)

**C. Dodanie do Portainer:**

1. W Portainer → **Stacks** → **monitoring** → **Editor**
2. Dodaj zmienne środowiskowe:
   - `TELEGRAM_BOT_TOKEN` = `twój_token_z_botfather`
   - `TELEGRAM_CHAT_ID` = `twój_chat_id`
3. Kliknij **Update the stack**
4. Sprawdź logi `telegram-webhook` serwisu - powinno być: `✅ Telegram credentials configured`

### Krok 7: Konfiguracja Uptime Kuma

1. Otwórz Uptime Kuma: `https://<MONITORING_HOST>/uptime-kuma`
2. Przy pierwszym uruchomieniu utwórz konto administratora
3. Dodaj monitorowane serwisy:
   - Kliknij **Add Monitor**
   - **Type**: HTTP(s)
   - **URL**: URL serwisu do monitorowania
   - **Interval**: 60 sekund
   - **Retries**: 2
4. (Opcjonalnie) Skonfiguruj auto-restart:
   - Zobacz [ALERTING.md](docs/ALERTING.md) - sekcja "Uptime Kuma Auto-Restart"

### Krok 8: Konfiguracja Duplicati (Backup)

1. Otwórz Duplicati: `https://<MONITORING_HOST>/duplicati`
2. Przy pierwszym uruchomieniu utwórz konto administratora
3. Utwórz nowy backup job:
   - Kliknij **Add backup**
   - **Source**: Wybierz volumes z `/source/`:
     - `/source/prometheus` → Prometheus data
     - `/source/grafana` → Grafana data
     - `/source/loki` → Loki data
     - `/source/uptime-kuma` → Uptime Kuma data
     - `/source/alertmanager` → Alertmanager data
   - **Destination**: Wybierz storage (S3, FTP, Google Drive, etc.)
   - **Schedule**: Ustaw harmonogram (np. codziennie o 2:00)
4. Zapisz i uruchom pierwszy backup

### Krok 9: Dostęp do serwisów

Po wdrożeniu, wszystkie serwisy są dostępne przez Traefik HTTPS:

- **Grafana**: `https://<MONITORING_HOST>/grafana`
  - Login: `admin` / Hasło: (z `GRAFANA_ADMIN_PASSWORD`)
- **Prometheus**: `https://<MONITORING_HOST>/prometheus`
- **Alertmanager**: `https://<MONITORING_HOST>/alertmanager`
- **Loki**: `https://<MONITORING_HOST>/loki`
- **Uptime Kuma**: `https://<MONITORING_HOST>/uptime-kuma`
- **Duplicati**: `https://<MONITORING_HOST>/duplicati`

### Krok 10: Konfiguracja automatycznego wdrożenia (opcjonalnie)

**Automatyczne wdrożenie przez GitHub Actions:**

1. W Portainer → **Stacks** → **monitoring** → **Webhooks**
2. Kliknij **Add webhook** (jeśli nie ma jeszcze webhooka)
3. Skopiuj **Webhook URL** (format: `http://57.129.41.248:9000/api/stacks/webhooks/xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
4. W GitHub → **Settings** → **Secrets and variables** → **Actions**
5. Kliknij **New repository secret**
6. **Name**: `PORTAINER_MONITORING_WEBHOOK`
7. **Secret**: Wklej webhook URL z Portainera
8. Kliknij **Add secret**

**Po skonfigurowaniu:**
- Każdy push do branch `main` automatycznie aktualizuje stack w Portainer
- GitHub Actions waliduje konfigurację przed wdrożeniem
- Szczegóły: [.github/SECRETS.md](.github/SECRETS.md)

### Krok 11: Aktualizacja stacku

**Automatyczna aktualizacja (jeśli skonfigurowano webhook):**

1. Wprowadź zmiany w `docker-compose.yml` lub plikach konfiguracyjnych
2. Zcommit i push do `main`:
   ```bash
   git add .
   git commit -m "feat: update monitoring configuration"
   git push origin main
   ```
3. GitHub Actions automatycznie:
   - Waliduje konfigurację
   - Wywołuje webhook Portainera
   - Portainer aktualizuje stack

**Ręczna aktualizacja przez Portainer:**

1. W Portainer → **Stacks** → **monitoring**
2. Kliknij **Editor**
3. Zaktualizuj `docker-compose.yml` (np. wklej nową wersję)
4. Zaktualizuj zmienne środowiskowe jeśli potrzeba
5. Kliknij **Update the stack**

**Aktualizacja przez Git (jeśli używasz Git repository):**

1. W Portainer → **Stacks** → **monitoring**
2. Kliknij **Editor**
3. Kliknij **Pull and redeploy** (jeśli masz auto-update wyłączone)
4. Lub: włącz **Auto-update** w ustawieniach stacku

### Troubleshooting

**Problem: Serwis nie startuje**

1. W Portainer → **Stacks** → **monitoring** → kliknij na serwis
2. Sprawdź **Logs** - znajdź błąd
3. Sprawdź **Inspect** - sprawdź konfigurację
4. Sprawdź czy wszystkie zmienne środowiskowe są ustawione

**Problem: Nie mogę się połączyć z serwisem przez Traefik**

1. Sprawdź czy Traefik działa: `docker service ls | grep traefik`
2. Sprawdź czy sieć `traefik-public` istnieje
3. Sprawdź logi Traefik: `docker service logs traefik`
4. Sprawdź czy serwis ma poprawne Traefik labels w `docker-compose.yml`

**Problem: Brak metryk w Prometheus**

1. Sprawdź logi Prometheus: `docker service logs monitoring_prometheus`
2. Sprawdź targets w Prometheus: `https://<MONITORING_HOST>/prometheus/targets`
3. Sprawdź czy kontenery mają label `prometheus.io/scrape=true`

**Problem: Alerty nie są wysyłane do Telegram**

1. Sprawdź logi telegram-webhook: `docker service logs monitoring_telegram-webhook`
2. Sprawdź czy `TELEGRAM_BOT_TOKEN` i `TELEGRAM_CHAT_ID` są ustawione
3. Sprawdź czy bot ma dostęp do czatu/kanału
4. Sprawdź status Alertmanager: `https://<MONITORING_HOST>/alertmanager`

### Instalacja lokalna (alternatywa)

Jeśli nie używasz Portainera, możesz wdrożyć lokalnie:

```bash
# 1. Sklonuj repozytorium
git clone <repository-url>
cd vps-monitoring

# 2. Skonfiguruj zmienne
cp env.portainer.example .env
nano .env  # Edytuj zmienne

# 3. Wdróż stack
docker stack deploy -c docker-compose.yml monitoring

# 4. Sprawdź status
docker service ls | grep monitoring
```

## 🔗 Dostęp do serwisów

Wszystkie serwisy są dostępne przez Traefik HTTPS:

- **Grafana**: `https://<MONITORING_HOST>/grafana` (domyślnie: admin/admin)
- **Prometheus**: `https://<MONITORING_HOST>/prometheus`
- **Alertmanager**: `https://<MONITORING_HOST>/alertmanager`
- **Loki**: `https://<MONITORING_HOST>/loki`
- **Uptime Kuma**: `https://<MONITORING_HOST>/uptime-kuma`
- **Duplicati**: `https://<MONITORING_HOST>/duplicati`

Bezpośredni dostęp (porty):
- Grafana: `http://<MONITORING_HOST>:3000`
- Prometheus: `http://<MONITORING_HOST>:9090`
- Alertmanager: `http://<MONITORING_HOST>:9093`
- Telegram Webhook: `http://<MONITORING_HOST>:8080`
- Blackbox Exporter: `http://<MONITORING_HOST>:9115`
- Uptime Kuma: `http://<MONITORING_HOST>:3001`
- Duplicati: `http://<MONITORING_HOST>:8200`

## 🎯 Automatyczne wykrywanie kontenerów

### Konfiguracja kontenerów do monitorowania

Aby automatycznie monitorować kontener, dodaj następujące labels do serwisu w Docker Swarm:

```yaml
labels:
  - "prometheus.io/scrape=true"
  - "prometheus.io/port=9090"          # Opcjonalnie, domyślnie 9090
  - "prometheus.io/path=/metrics"       # Opcjonalnie, domyślnie /metrics
  - "app.name=wordpress-production"     # Nazwa aplikacji
  - "app.type=wordpress"                # Typ aplikacji (wordpress, database, api, etc.)
```

### Automatyczne tworzenie dashboardów

Serwis `dashboard-automation` (Python) działa jako osobny kontener w stacku:

**Mechanizm działania:**
1. Co 60 sekund sprawdza Prometheus API (`/api/v1/targets`)
2. Wykrywa nowe aktywne targets z labelami:
   - `prometheus.io/scrape=true` (już wykrywane przez Prometheus)
   - `app.name` - nazwa aplikacji (np. `wordpress-production`)
   - `app.type` - typ aplikacji (np. `wordpress`, `api`, `database`)
3. Dla każdego nowo wykrytego serwisu:
   - Sprawdza czy dashboard już istnieje (przez Grafana API)
   - Jeśli nie istnieje, pobiera odpowiedni template z `config/grafana/provisioning/dashboards/templates/`
   - Wypełnia template zmiennymi z labelów Prometheus:
     - `{{app.name}}` → nazwa serwisu
     - `{{app.type}}` → typ aplikacji
     - `{{container.name}}` → nazwa kontenera
     - `{{job}}` → job name z Prometheus
   - Tworzy dashboard przez Grafana HTTP API (`POST /api/dashboards/db`)
   - Ustawia folder dashboardu na podstawie `app.type` (np. WordPress, Generic, Database)

**Dostępne template dashboardów:**
- `wordpress.json` - template dla WordPress (CPU, memory, Redis, OPcache, MariaDB, request rate)
- `generic-app.json` - uniwersalny template (CPU, memory, network, disk I/O)
- `database.json` - template dla baz danych (CPU, memory, disk I/O Read/Write)

**Konfiguracja przez zmienne środowiskowe:**
- `GRAFANA_URL` - URL Grafana API (http://grafana:3000)
- `GRAFANA_ADMIN_USER` - użytkownik admin Grafana
- `GRAFANA_ADMIN_PASSWORD` - hasło admin Grafana
- `PROMETHEUS_URL` - URL Prometheus API (http://prometheus:9090)
- `CHECK_INTERVAL` - interwał sprawdzania (domyślnie 60s)

## 📁 Struktura projektu

```
vps-monitoring/
├── docker-compose.yml              # Docker Swarm stack (9 serwisów)
├── .env.example                    # Template zmiennych środowiskowych
├── README.md                       # Ten plik
├── config/
│   ├── prometheus/
│   │   └── prometheus.yml          # Konfiguracja Prometheus z Docker Swarm Service Discovery
│   ├── loki/
│   │   └── loki-config.yaml        # Konfiguracja Loki (retention, limits, storage)
│   ├── promtail/
│   │   └── promtail-config.yaml    # Konfiguracja Promtail (scraping logów Docker)
│   └── grafana/
│       └── provisioning/
│           ├── datasources/
│           │   └── datasources.yml # Auto-konfiguracja Prometheus i Loki
│           └── dashboards/
│               ├── dashboards.yml  # Auto-ładowanie dashboardów
│               ├── default/        # Folder na preloadowane dashboardy
│               └── templates/      # Template dla auto-dashboardów
│                   ├── wordpress.json
│                   ├── generic-app.json
│                   └── database.json
├── docs/
│   ├── DEPLOYMENT.md               # Instrukcje wdrożenia na Docker Swarm
│   └── CONFIGURATION.md            # Szczegóły konfiguracji każdego komponentu
├── scripts/
│   ├── dashboard-automation.py     # Skrypt automatycznego tworzenia dashboardów
│   └── deploy.sh                   # Skrypt wdrożenia i zarządzania stackiem
└── .github/
    ├── workflows/
    │   ├── validate.yml            # Walidacja konfiguracji przy PR
    │   └── deploy.yml               # Automatyczne wdrożenie do Portainera
    └── SECRETS.md                   # Dokumentacja konfiguracji GitHub Secrets
```

## ⚙️ Konfiguracja

### Prometheus

**Docker Swarm Service Discovery:**
- Automatyczne wykrywanie kontenerów Docker Swarm przez `dockerswarm_sd_configs`
- Relabeling rules do filtrowania kontenerów przez labels
- Kontenery z label `prometheus.io/scrape=true` są automatycznie dodawane
- Automatyczne wykrywanie portów z label `prometheus.io/port` (domyślnie 9090)
- Automatyczne wykrywanie ścieżek z label `prometheus.io/path` (domyślnie `/metrics`)

**Retention:** 30 dni (720h) - konfigurowalne przez `PROMETHEUS_RETENTION`
**Scrape interval:** 30s
**Evaluation interval:** 15s

### Loki

- Schema config z timestamps
- Storage config (loki_data volume)
- Retention: 30 dni (720h) - konfigurowalne przez `LOKI_RETENTION_DAYS`
- Limits dla performance (ingestion rate, burst size, max query parallelism)

### Promtail

- Scraping logów z `/var/lib/docker/containers`
- Parsowanie logów JSON
- Labeling kontenerów (container_name, service_name, app_name, app_type)
- Wysyłanie do Loki

### Grafana Provisioning

**Auto-provisioning:**
- Datasources: Prometheus i Loki są automatycznie konfigurowane
- Dashboards: auto-ładowanie z folderów `default/` i `templates/`
- Template dashboardów dla automatycznego tworzenia nowych dashboardów

**Szczegółowa konfiguracja dostępna w:**
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - Instrukcje wdrożenia
- [CONFIGURATION.md](docs/CONFIGURATION.md) - Szczegóły konfiguracji każdego komponentu

## 🔧 Zmienne środowiskowe

Główne zmienne (zobacz `env.portainer.example`):

- `GRAFANA_ADMIN_PASSWORD` - hasło admin Grafana
- `MONITORING_HOST` - IP hosta dla Traefik routing
- `PROMETHEUS_RETENTION` - retention danych Prometheus (domyślnie 720h = 30 dni)
- `LOKI_RETENTION_DAYS` - retention logów Loki (domyślnie 720h = 30 dni)
- `CHECK_INTERVAL` - interwał sprawdzania nowych kontenerów (domyślnie 60s)
- `TELEGRAM_BOT_TOKEN` - token bota Telegram (z @BotFather)
- `TELEGRAM_CHAT_ID` - ID czatu/channelu dla powiadomień

## 📈 Monitoring

### Prometheus Targets

Sprawdź wykryte targets:
```bash
curl http://localhost:9090/api/v1/targets | jq
```

### Grafana Dashboards

Po wdrożeniu, dashboardy są automatycznie tworzone dla kontenerów z odpowiednimi labelami.

### Logi

Wszystkie logi są zbierane przez Promtail i dostępne w Loki przez Grafana.

## 🚨 System Alertów

### Monitoring Alertów

System monitoruje i alertuje o:

- **Krytyczne zużycie CPU** (>90% przez 5 min)
- **Krytyczne zużycie RAM** (>90% przez 5 min)
- **Krytyczne zużycie dysku** (<10% dostępnego miejsca)
- **Błędy HTTP 4xx** (>10 errors/sec przez 5 min)
- **Błędy HTTP 5xx** (>5 errors/sec przez 5 min)
- **Serwis nieaktywny** (serwis padł/nie odpowiada)
- **Traefik metrics** (wysoki request rate, wysokie response time, endpoint down)

### Powiadomienia Telegram

Wszystkie alerty są wysyłane przez Telegram:
1. Skonfiguruj bota Telegram (zobacz [ALERTING.md](docs/ALERTING.md))
2. Dodaj `TELEGRAM_BOT_TOKEN` i `TELEGRAM_CHAT_ID` do zmiennych środowiskowych
3. Alerty będą automatycznie wysyłane do Telegram

### Uptime Kuma Auto-Restart

Uptime Kuma może automatycznie restartować serwisy które padły:
- Skonfiguruj webhook w Uptime Kuma
- Połącz z Docker API lub Portainer API
- Serwisy będą automatycznie restartowane przy wykryciu problemu

Szczegółowa konfiguracja: [ALERTING.md](docs/ALERTING.md)

## 🗄️ Backup

Duplicati jest skonfigurowany do backupowania:
- Prometheus data (`prometheus_data`)
- Grafana data (`grafana_data`)
- Loki data (`loki_data`)
- Uptime Kuma data (`uptime_kuma_data`)

Konfiguracja backupów przez interfejs webowy Duplicati.

## 🔄 Aktualizacja

### Ręczna aktualizacja

```bash
docker stack deploy -c docker-compose.yml monitoring
```

### Automatyczna aktualizacja przez GitHub Actions

Po skonfigurowaniu webhooka Portainera, każdy push do `main` automatycznie aktualizuje stack.

## 🏗️ Architektura

### Kluczowe decyzje techniczne

- **Docker Swarm** (nie Compose) - zgodnie z istniejącym stackiem
- **Volumes** dla danych persistent:
  - `prometheus_data` - dane Prometheus
  - `grafana_data` - dane Grafana (dashboards, datasources, users)
  - `loki_data` - dane Loki (chunks, index)
  - `uptime_kuma_data` - dane Uptime Kuma
  - `duplicati_data` - konfiguracja Duplicati
  - `duplicati_backups` - backupowane dane
- **Network `monitoring`** (overlay) + `traefik-public` (external)
- **Restart policy:** `condition: any` z delay 5s
- **Placement constraints:** manager nodes dla głównych serwisów
- **Global mode:** promtail i cadvisor (jeden na każdym nodzie)

## 🐛 Troubleshooting

### Sprawdź logi serwisów:
```bash
docker service logs monitoring_prometheus
docker service logs monitoring_grafana
docker service logs monitoring_alertmanager
docker service logs monitoring_telegram-webhook
docker service logs monitoring_dashboard-automation
```

### Sprawdź status serwisów:
```bash
docker service ps monitoring_prometheus
docker service ps monitoring_grafana
```

## 📚 Dokumentacja

- [README.md](README.md) - Ten plik - overview i quick start
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - Szczegółowe instrukcje wdrożenia na Docker Swarm
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - Szczegóły konfiguracji każdego komponentu
- [docs/ALERTING.md](docs/ALERTING.md) - Konfiguracja alertów i powiadomień Telegram
- [.github/SECRETS.md](.github/SECRETS.md) - Konfiguracja GitHub Secrets i Portainer webhooks

## 🔄 CI/CD Pipeline

### GitHub Actions Workflows

**Automatic Validation:**
- Pull requests are automatically validated
- Checks docker-compose.yml syntax
- Validates all configuration files
- Non-blocking warnings

**Automatic Deployment:**
- Push to `main` branch triggers deployment
- Validates stack configuration
- Triggers Portainer webhook to update stack
- Non-blocking (webhook failure doesn't fail workflow)

### Setup

1. **Configure GitHub Secret:**
   - Add `PORTAINER_MONITORING_WEBHOOK` secret
   - Get webhook URL from Portainer (Stack → Webhooks)
   - See [.github/SECRETS.md](.github/SECRETS.md) for details

2. **Configure Portainer Stack:**
   - Create stack in Portainer with "Repository" method
   - Point to your GitHub repository
   - Set branch to `main`
   - Compose path: `docker-compose.yml`

3. **Deploy:**
   - Push changes to `main` branch
   - GitHub Actions validates and triggers webhook
   - Portainer automatically updates the stack

See [.github/SECRETS.md](.github/SECRETS.md) for detailed setup instructions.

## 📝 Licencja

MIT
