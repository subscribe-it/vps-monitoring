# Proces Deployu Stacku Monitoringu w Portainer

## 📋 Przegląd

Ten dokument szczegółowo opisuje proces wdrożenia stacku Docker Swarm w Portainer z Git repository, krok po kroku.

## 🚀 Proces Deployu - Krok po Kroku

### Faza 1: Przygotowanie (Pierwszy Deploy)

#### 1.1. Konfiguracja Stacku w Portainer

**W Portainer:**
1. **Stacks** → **Add stack**
2. **Name**: `monitoring`
3. **Type**: `Docker Swarm`
4. **Build method**: `Repository` (Git)

**Konfiguracja Git:**
- **Repository URL**: `https://github.com/username/vps-monitoring` (lub SSH)
- **Repository reference**: `main` (branch/tag)
- **Compose path**: `docker-compose.yml`
- **Auto-update**: `Enabled` (opcjonalnie, webhook jest lepszy)

**Environment variables** (dodaj w Portainer):
```env
GRAFANA_ADMIN_PASSWORD=secure_password
MONITORING_HOST=57.129.41.248
PROMETHEUS_RETENTION=720h
LOKI_RETENTION_DAYS=720
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=123456789
GRAFANA_URL=http://grafana:3000
PROMETHEUS_URL=http://prometheus:9090
CHECK_INTERVAL=60
```

#### 1.2. Portainer Pobiera Pliki z Git

**Co się dzieje:**
1. Portainer wykonuje `git clone` (lub `git pull` jeśli już istnieje)
2. Pobiera `docker-compose.yml` z branch `main`
3. Pobiera wszystkie pliki konfiguracyjne z `config/`:
   - `config/prometheus/prometheus.yml`
   - `config/prometheus/alerts/*.yml`
   - `config/loki/loki-config.yaml`
   - `config/promtail/promtail-config.yaml`
   - `config/alertmanager/alertmanager.yml`
   - `config/blackbox/blackbox.yml`
   - `config/grafana/provisioning/**`
4. Pobiera skrypty z `scripts/`:
   - `scripts/telegram-webhook.py`
   - `scripts/dashboard-automation.py`
   - `scripts/requirements.txt`

**Ważne:**
- Portainer **NIE** build'uje obrazów - tylko pobiera pliki
- Wszystkie pliki są dostępne lokalnie na VPS (cache'owane przez Portainer)

### Faza 2: Parsowanie i Walidacja

#### 2.1. Parsowanie docker-compose.yml

Portainer analizuje `docker-compose.yml` i wyodrębnia:

**Networks:**
- `monitoring` (overlay, attachable) - nowa sieć
- `traefik-public` (external) - istniejąca sieć Traefik

**Volumes:**
- `prometheus_data` - nowy volume
- `grafana_data` - nowy volume
- `loki_data` - nowy volume
- `uptime_kuma_data` - nowy volume
- `duplicati_data` - nowy volume
- `duplicati_backups` - nowy volume
- `alertmanager_data` - nowy volume

**Services:** 12 serwisów (node-exporter, cadvisor, prometheus, loki, promtail, grafana, uptime-kuma, duplicati, alertmanager, blackbox-exporter, telegram-webhook, dashboard-automation)

#### 2.2. Walidacja

Portainer sprawdza:
- ✅ Składnię YAML
- ✅ Czy wszystkie referenced networks istnieją (lub mogą być utworzone)
- ✅ Czy wszystkie pliki konfiguracyjne są dostępne
- ✅ Czy zmienne środowiskowe są zdefiniowane
- ⚠️ **NIE** sprawdza czy obrazy Docker istnieją (sprawdzi to Docker przy pull)

### Faza 3: Tworzenie Infrastruktury

#### 3.1. Utworzenie Sieci

**Portainer wykonuje:**
```bash
# Network: monitoring
docker network create \
  --driver overlay \
  --attachable \
  --scope swarm \
  monitoring_monitoring

# Network: traefik-public (jeśli nie istnieje, Portainer zwróci błąd)
# To jest external network - musi istnieć wcześniej
```

**Rezultat:**
- ✅ Sieć `monitoring_monitoring` utworzona (prefiks `monitoring_` = nazwa stacku)
- ✅ Sieć `traefik-public` jest używana (external)

#### 3.2. Utworzenie Volumes

**Portainer wykonuje dla każdego volume:**
```bash
docker volume create monitoring_prometheus_data
docker volume create monitoring_grafana_data
docker volume create monitoring_loki_data
docker volume create monitoring_uptime_kuma_data
docker volume create monitoring_duplicati_data
docker volume create monitoring_duplicati_backups
docker volume create monitoring_alertmanager_data
```

**Rezultat:**
- ✅ 7 volumes utworzonych (prefiks `monitoring_` = nazwa stacku)
- ✅ Volumes są persistent - dane przetrwają restart stacku

### Faza 4: Pobieranie Obrazów Docker

**Portainer automatycznie wykonuje `docker pull` dla każdego obrazu:**

#### 4.1. Lista Obrazów do Pobrania

Dla każdego serwisu Portainer analizuje `image:` i wykonuje pull:

```bash
# Global services (1 na każdym nodzie)
docker pull prom/node-exporter:latest
docker pull gcr.io/cadvisor/cadvisor:v0.47.0

# Replicated services (1 replika)
docker pull prom/prometheus:latest
docker pull grafana/loki:latest
docker pull grafana/promtail:latest
docker pull grafana/grafana:latest
docker pull louislam/uptime-kuma:latest
docker pull lscr.io/linuxserver/duplicati:latest
docker pull prom/alertmanager:latest
docker pull prom/blackbox-exporter:latest
docker pull python:3.11-slim  # x2 (telegram-webhook, dashboard-automation)
```

**Łącznie: 11 unikalnych obrazów**

#### 4.2. Proces Pull

**Dla każdego obrazu:**
1. Portainer sprawdza czy obraz już istnieje lokalnie (cache)
2. Jeśli nie ma lub tag się zmienił → `docker pull <image>`
3. Obrazy są pobierane z rejestrów:
   - Docker Hub: `prom/`, `grafana/`, `louislam/`
   - Google Container Registry: `gcr.io/`
   - LinuxServer.io: `lscr.io/`
   - Python official: `python:`

**Ważne:**
- ✅ **Publiczne obrazy** - działają automatycznie
- ⚠️ **Prywatne obrazy** (np. z ghcr.io) - wymagają Registry authentication w Portainer
- ⏱️ Pull może zająć kilka minut (zależnie od rozmiaru obrazów i szybkości internetu)

#### 4.3. Cache Obrazów

- Obrazy są cache'owane lokalnie na VPS
- Przy kolejnych deployach Portainer sprawdza czy tag się zmienił
- Jeśli tag jest taki sam → używa cache'u (szybciej)
- Jeśli tag się zmienił → pull nowej wersji

### Faza 5: Tworzenie Serwisów (Docker Swarm Services)

**Portainer tworzy serwisy w kolejności zdefiniowanej w `docker-compose.yml`, ale Docker Swarm obsługuje zależności (`depends_on`) automatycznie.**

#### 5.1. Global Services (mode: global)

**Node Exporter** - uruchamiany na każdym nodzie:
```bash
docker service create \
  --name monitoring_node-exporter \
  --mode global \
  --network monitoring_monitoring \
  --mount type=bind,source=/proc,target=/host/proc,readonly \
  --mount type=bind,source=/sys,target=/host/sys,readonly \
  --mount type=bind,source=/,target=/rootfs,readonly \
  --publish mode=host,target=9100,published=9100 \
  --restart-condition any \
  --restart-delay 5s \
  prom/node-exporter:latest \
  --path.procfs=/host/proc \
  --path.rootfs=/rootfs \
  --path.sysfs=/host/sys \
  --collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc|$$)
```

**cAdvisor** - uruchamiany na każdym nodzie:
```bash
docker service create \
  --name monitoring_cadvisor \
  --mode global \
  --network monitoring_monitoring \
  --mount type=bind,source=/,target=/rootfs,readonly \
  --mount type=bind,source=/var/run,target=/var/run,readonly \
  --mount type=bind,source=/sys,target=/sys,readonly \
  --mount type=bind,source=/var/lib/docker,target=/var/lib/docker,readonly \
  --mount type=bind,source=/dev/disk,target=/dev/disk,readonly \
  --publish mode=host,target=8080,published=8081 \
  --restart-condition any \
  --restart-delay 5s \
  gcr.io/cadvisor/cadvisor:v0.47.0 \
  --docker_only=true \
  --housekeeping_interval=30s \
  --disable_metrics=percpu,sched,tcp,udp,disk,diskIO,hugetlb \
  --store_container_labels=false
```

#### 5.2. Replicated Services (replicas: 1)

**Alertmanager** (uruchamiany pierwszy, bo inne serwisy zależą od niego):
```bash
docker service create \
  --name monitoring_alertmanager \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --network traefik-public \
  --mount type=bind,source=/path/to/config/alertmanager/alertmanager.yml,target=/etc/alertmanager/alertmanager.yml,readonly \
  --mount type=volume,source=monitoring_alertmanager_data,target=/alertmanager \
  --publish 9093:9093 \
  --restart-condition any \
  --restart-delay 5s \
  --limit-cpu 0.25 \
  --limit-memory 256M \
  --reserve-cpu 0.1 \
  --reserve-memory 64M \
  --health-cmd "wget --no-verbose --tries=1 --spider http://localhost:9093/-/healthy || exit 1" \
  --health-interval 30s \
  --health-timeout 10s \
  --health-retries 3 \
  --health-start-period 40s \
  prom/alertmanager:latest \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --storage.path=/alertmanager \
  --web.external-url=http://57.129.41.248:9093
```

**Blackbox Exporter:**
```bash
docker service create \
  --name monitoring_blackbox-exporter \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --mount type=bind,source=/path/to/config/blackbox/blackbox.yml,target=/etc/blackbox_exporter/config.yml,readonly \
  --publish 9115:9115 \
  --restart-condition any \
  --restart-delay 5s \
  prom/blackbox-exporter:latest \
  --config.file=/etc/blackbox_exporter/config.yml
```

**Prometheus** (zależy od alertmanager i blackbox-exporter):
```bash
docker service create \
  --name monitoring_prometheus \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --network traefik-public \
  --mount type=bind,source=/path/to/config/prometheus/prometheus.yml,target=/etc/prometheus/prometheus.yml,readonly \
  --mount type=bind,source=/path/to/config/prometheus/alerts,target=/etc/prometheus/alerts,readonly \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock,readonly \
  --mount type=volume,source=monitoring_prometheus_data,target=/prometheus \
  --publish 9090:9090 \
  --restart-condition any \
  --restart-delay 5s \
  --limit-cpu 1 \
  --limit-memory 2G \
  --reserve-cpu 0.5 \
  --reserve-memory 512M \
  --health-cmd "wget --no-verbose --tries=1 --spider http://localhost:9090/-/healthy || exit 1" \
  prom/prometheus:latest \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time=720h \
  --web.enable-lifecycle
```

**Loki:**
```bash
docker service create \
  --name monitoring_loki \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --network traefik-public \
  --mount type=bind,source=/path/to/config/loki/loki-config.yaml,target=/etc/loki/local-config.yaml,readonly \
  --mount type=volume,source=monitoring_loki_data,target=/loki \
  --publish 3100:3100 \
  --restart-condition any \
  --restart-delay 5s \
  --limit-cpu 0.5 \
  --limit-memory 1G \
  --reserve-cpu 0.25 \
  --reserve-memory 256M \
  --health-cmd "wget --no-verbose --tries=1 --spider http://localhost:3100/ready || exit 1" \
  grafana/loki:latest \
  -config.file=/etc/loki/local-config.yaml
```

**Promtail** (global mode, zależy od loki):
```bash
docker service create \
  --name monitoring_promtail \
  --mode global \
  --network monitoring_monitoring \
  --mount type=bind,source=/path/to/config/promtail/promtail-config.yaml,target=/etc/promtail/config.yml,readonly \
  --mount type=bind,source=/var/log,target=/var/log,readonly \
  --mount type=bind,source=/var/lib/docker/containers,target=/var/lib/docker/containers,readonly \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock,readonly \
  --restart-condition any \
  --restart-delay 5s \
  grafana/promtail:latest \
  -config.file=/etc/promtail/config.yml
```

**Grafana** (zależy od prometheus i loki):
```bash
docker service create \
  --name monitoring_grafana \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --network traefik-public \
  --mount type=volume,source=monitoring_grafana_data,target=/var/lib/grafana \
  --mount type=bind,source=/path/to/config/grafana/provisioning,target=/etc/grafana/provisioning,readonly \
  --mount type=bind,source=/path/to/config/grafana/provisioning/dashboards/default,target=/var/lib/grafana/dashboards/default,readonly \
  --mount type=bind,source=/path/to/config/grafana/provisioning/dashboards/templates,target=/var/lib/grafana/dashboards/templates,readonly \
  --publish 3000:3000 \
  --restart-condition any \
  --restart-delay 5s \
  --limit-cpu 0.5 \
  --limit-memory 512M \
  --reserve-cpu 0.25 \
  --reserve-memory 128M \
  --health-cmd "wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1" \
  --env GF_SECURITY_ADMIN_PASSWORD=secure_password \
  --env GF_USERS_ALLOW_SIGN_UP=false \
  --env GF_AUTH_ANONYMOUS_ENABLED=false \
  grafana/grafana:latest
```

**Uptime Kuma:**
```bash
docker service create \
  --name monitoring_uptime-kuma \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --network traefik-public \
  --mount type=volume,source=monitoring_uptime_kuma_data,target=/app/data \
  --publish 3001:3001 \
  --restart-condition any \
  --restart-delay 5s \
  louislam/uptime-kuma:latest
```

**Duplicati:**
```bash
docker service create \
  --name monitoring_duplicati \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --network traefik-public \
  --mount type=volume,source=monitoring_duplicati_data,target=/config \
  --mount type=volume,source=monitoring_duplicati_backups,target=/backups \
  --mount type=volume,source=monitoring_prometheus_data,target=/source/prometheus,readonly \
  --mount type=volume,source=monitoring_grafana_data,target=/source/grafana,readonly \
  --mount type=volume,source=monitoring_loki_data,target=/source/loki,readonly \
  --mount type=volume,source=monitoring_uptime_kuma_data,target=/source/uptime-kuma,readonly \
  --mount type=volume,source=monitoring_alertmanager_data,target=/source/alertmanager,readonly \
  --publish 8200:8200 \
  --restart-condition any \
  --restart-delay 5s \
  --env PUID=1000 \
  --env PGID=1000 \
  --env TZ=Europe/Warsaw \
  lscr.io/linuxserver/duplicati:latest
```

**Telegram Webhook:**
```bash
docker service create \
  --name monitoring_telegram-webhook \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --mount type=bind,source=/path/to/scripts/telegram-webhook.py,target=/app/telegram-webhook.py,readonly \
  --mount type=bind,source=/path/to/scripts/requirements.txt,target=/app/requirements.txt,readonly \
  --publish 8088:8088 \
  --restart-condition any \
  --restart-delay 5s \
  --limit-cpu 0.25 \
  --limit-memory 128M \
  --reserve-cpu 0.1 \
  --reserve-memory 32M \
  --health-cmd "wget --no-verbose --tries=1 --spider http://localhost:8088/health || exit 1" \
  --env TELEGRAM_BOT_TOKEN=123456789:ABC... \
  --env TELEGRAM_CHAT_ID=123456789 \
  --env PORT=8088 \
  python:3.11-slim \
  sh -c "pip install -q -r requirements.txt && python3 telegram-webhook.py"
```

**Dashboard Automation:**
```bash
docker service create \
  --name monitoring_dashboard-automation \
  --replicas 1 \
  --constraint 'node.role == manager' \
  --network monitoring_monitoring \
  --mount type=bind,source=/path/to/scripts/dashboard-automation.py,target=/app/dashboard-automation.py,readonly \
  --mount type=bind,source=/path/to/config/grafana/provisioning/dashboards/templates,target=/app/templates,readonly \
  --restart-condition any \
  --restart-delay 5s \
  --limit-cpu 0.25 \
  --limit-memory 256M \
  --reserve-cpu 0.1 \
  --reserve-memory 64M \
  --env GRAFANA_URL=http://grafana:3000 \
  --env GRAFANA_ADMIN_USER=admin \
  --env GRAFANA_ADMIN_PASSWORD=secure_password \
  --env PROMETHEUS_URL=http://prometheus:9090 \
  --env CHECK_INTERVAL=60 \
  python:3.11-slim \
  python3 dashboard-automation.py
```

#### 5.3. Traefik Labels (Routing)

**Dla każdego serwisu z Traefik labels:**
- Portainer automatycznie rejestruje serwisy w Traefik
- Traefik wykrywa nowe serwisy przez Docker Swarm service discovery
- Routing działa automatycznie (np. `/grafana` → Grafana)

**Przykład dla Grafana:**
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.services.grafana.loadbalancer.server.port=3000"
  - "traefik.http.routers.grafana.rule=Host(57.129.41.248) && PathPrefix(/grafana)"
  - "traefik.http.routers.grafana.entrypoints=websecure"
  - "traefik.http.routers.grafana.middlewares=grafana-stripprefix"
  - "traefik.http.middlewares.grafana-stripprefix.stripprefix.prefixes=/grafana"
```

**Co się dzieje:**
1. Traefik wykrywa nowy serwis `monitoring_grafana`
2. Czyta labels i konfiguruje routing:
   - HTTPS (`websecure` entrypoint)
   - Host: `57.129.41.248`
   - Path: `/grafana` → strip prefix → `/` do Grafana
3. SSL certificate jest automatycznie generowany przez Let's Encrypt (jeśli skonfigurowane)

### Faza 6: Health Checks i Startup

#### 6.1. Health Checks

**Serwisy z healthcheck:**
- Prometheus: `wget http://localhost:9090/-/healthy`
- Loki: `wget http://localhost:3100/ready`
- Grafana: `wget http://localhost:3000/api/health`
- Alertmanager: `wget http://localhost:9093/-/healthy`
- Telegram Webhook: `wget http://localhost:8088/health`

**Docker Swarm:**
- Sprawdza healthcheck co `interval` (30s)
- Jeśli healthcheck fail → restart kontenera
- Jeśli healthcheck pass → kontener jest "healthy"

#### 6.2. Startup Sequence

**Kolejność uruchamiania (zależności):**

1. **Global services** (uruchamiane równolegle):
   - `node-exporter` (global)
   - `cadvisor` (global)

2. **Base services**:
   - `alertmanager` (bez zależności)
   - `blackbox-exporter` (bez zależności)

3. **Core services** (zależne od base):
   - `prometheus` (depends_on: alertmanager, blackbox-exporter)
   - `loki` (depends_on: node-exporter)

4. **Logging** (zależne od loki):
   - `promtail` (depends_on: loki, global)

5. **Visualization** (zależne od prometheus i loki):
   - `grafana` (depends_on: prometheus, loki)

6. **Additional services**:
   - `uptime-kuma` (bez zależności)
   - `duplicati` (bez zależności, ale mountuje volumes)
   - `telegram-webhook` (depends_on: alertmanager)
   - `dashboard-automation` (depends_on: grafana, prometheus)

**Ważne:**
- Docker Swarm **NIE** czeka na `depends_on` - to tylko informacja dla Portainer
- Serwisy startują równolegle, ale mogą mieć problemy jeśli zależności nie są gotowe
- Healthchecks pomagają w automatycznym recovery

### Faza 7: Inicjalizacja Danych

#### 7.1. Grafana Provisioning

**Grafana przy starcie:**
1. Sprawdza `/etc/grafana/provisioning/datasources/datasources.yml`
2. Automatycznie tworzy datasources:
   - Prometheus: `http://prometheus:9090`
   - Loki: `http://loki:3100`
3. Sprawdza `/etc/grafana/provisioning/dashboards/dashboards.yml`
4. Ładuje dashboardy z `/var/lib/grafana/dashboards/default/`

**Rezultat:**
- ✅ Datasources są gotowe od razu
- ✅ Dashboardy są dostępne od razu (bez ręcznej konfiguracji)

#### 7.2. Prometheus Scraping

**Prometheus przy starcie:**
1. Wczytuje `/etc/prometheus/prometheus.yml`
2. Wczytuje alert rules z `/etc/prometheus/alerts/*.yml`
3. Rozpoczyna scraping:
   - Static targets (node-exporter, cadvisor)
   - Docker Swarm Service Discovery (automatyczne wykrywanie)
4. Łączy się z Alertmanager: `http://alertmanager:9093`

**Rezultat:**
- ✅ Metryki są zbierane od razu
- ✅ Alerty są aktywne
- ✅ Automatyczne wykrywanie nowych kontenerów

#### 7.3. Dashboard Automation

**Dashboard Automation (Python script):**
1. Czeka 60 sekund (startup delay)
2. Sprawdza Prometheus API: `http://prometheus:9090/api/v1/targets`
3. Wykrywa nowe serwisy z labelami `app.name` i `app.type`
4. Tworzy dashboardy przez Grafana API
5. Powtarza co `CHECK_INTERVAL` (60s)

**Rezultat:**
- ✅ Automatyczne tworzenie dashboardów dla nowych serwisów

## 🔄 Proces Aktualizacji (Update)

### Update przez Webhook (GitHub Actions)

**Trigger:**
- Push do branch `main` w Git repository
- GitHub Actions waliduje konfigurację
- Jeśli OK → wywołuje Portainer webhook

**Portainer Webhook:**
1. **Pobiera najnowsze zmiany z Git:**
   ```bash
   git pull origin main
   ```

2. **Porównuje docker-compose.yml:**
   - Sprawdza czy coś się zmieniło
   - Jeśli nie → kończy (bez zmian)

3. **Jeśli są zmiany:**
   - **Obrazy:** Sprawdza czy `image:` tag się zmienił
   - **Konfiguracja:** Sprawdza czy pliki config się zmieniły
   - **Volumes:** Sprawdza czy volumes się zmieniły
   - **Networks:** Sprawdza czy networks się zmieniły

4. **Update Strategy:**
   - **Rolling Update** (domyślnie):
     - Tworzy nowy task z nowym obrazem/konfiguracją
     - Czeka aż healthcheck pass
     - Usuwa stary task
     - Zero-downtime update
   
   - **Recreate** (jeśli nie można rolling):
     - Zatrzymuje stary task
     - Tworzy nowy task
     - Może być krótki downtime

### Update przez Portainer UI

**Ręczna aktualizacja:**
1. **Stacks** → **monitoring** → **Editor**
2. **Pull and redeploy** (lub **Update the stack**)
3. Portainer wykonuje te same kroki co webhook

### Co się Aktualizuje

**Obrazy Docker:**
- Jeśli `image: prom/prometheus:latest` → Portainer sprawdza czy `latest` się zmienił
- Jeśli tag jest stały (np. `v2.40.0`) → pull tylko jeśli nie ma lokalnie
- Jeśli tag się zmienił → pull nowego obrazu i rolling update

**Konfiguracja:**
- Jeśli zmieniono `config/prometheus/prometheus.yml` → restart prometheus
- Jeśli zmieniono `config/grafana/provisioning/**` → restart grafana (reload provisioning)

**Zmienne środowiskowe:**
- Jeśli zmieniono env vars → restart serwisu (nowe env vars)

**Volumes:**
- Volumes są **NIE** usuwane przy update
- Dane są zachowane
- Jeśli usuniesz volume z docker-compose.yml → **UWAGA** - dane zostaną utracone!

## ⚠️ Ważne Uwagi

### 1. Volumes są Persistent

- **Volumes przetrwają restart stacku**
- **Volumes przetrwają update stacku**
- **Volumes NIE są usuwane automatycznie**

**Aby usunąć dane:**
```bash
docker stack rm monitoring
docker volume rm monitoring_prometheus_data
docker volume rm monitoring_grafana_data
# etc.
```

### 2. Networks są Persistent

- **Networks przetrwają restart stacku**
- **Networks są usuwane tylko gdy stack jest usunięty**

### 3. Obrazy są Cache'owane

- **Obrazy są przechowywane lokalnie na VPS**
- **Pull jest wykonywany tylko jeśli:**
  - Obraz nie istnieje lokalnie
  - Tag się zmienił (np. `latest` → nowszy build)

### 4. Healthchecks są Krytyczne

- **Healthchecks określają czy serwis jest "healthy"**
- **Unhealthy serwisy są automatycznie restartowane**
- **Startup delay (`start_period`) pozwala serwisom na inicjalizację**

### 5. Resource Limits

- **Resource limits są egzekwowane przez Docker Swarm**
- **Jeśli serwis przekroczy limit → throttling**
- **Reservations gwarantują minimum zasobów**

### 6. Placement Constraints

- **Serwisy z `node.role == manager` uruchamiane tylko na manager nodes**
- **Global services uruchamiane na wszystkich nodach**

## 📊 Timeline Deployu

**Typowy czas deployu (przy pierwszym deployu):**

```
0:00 - Portainer pobiera pliki z Git (10-30s)
0:30 - Parsowanie i walidacja (5-10s)
0:40 - Tworzenie sieci i volumes (5-10s)
0:50 - Pull obrazów Docker (2-10 minut, zależnie od rozmiaru)
3:00 - Tworzenie serwisów (1-2 minuty)
4:00 - Startup serwisów (30s - 2 min)
5:00 - Healthchecks pass (30s - 1 min)
6:00 - ✅ Stack gotowy
```

**Przy update (obrazy są cache'owane):**

```
0:00 - Portainer pobiera zmiany z Git (5-10s)
0:10 - Porównanie konfiguracji (5s)
0:15 - Pull nowych obrazów (jeśli potrzeba) (30s - 2 min)
2:00 - Rolling update serwisów (30s - 1 min)
3:00 - ✅ Update gotowy
```

## 🔍 Debugowanie Deployu

**Sprawdź status serwisów:**
```bash
docker stack services monitoring
docker service ps monitoring_prometheus
docker service logs monitoring_prometheus
```

**Sprawdź logi wszystkich serwisów:**
```bash
docker stack ps monitoring
docker service logs monitoring_prometheus --follow
docker service logs monitoring_grafana --follow
```

**Sprawdź czy obrazy są pobrane:**
```bash
docker images | grep prom
docker images | grep grafana
```

**Sprawdź volumes:**
```bash
docker volume ls | grep monitoring
docker volume inspect monitoring_prometheus_data
```

**Sprawdź networks:**
```bash
docker network ls | grep monitoring
docker network inspect monitoring_monitoring
```

## 🎯 Podsumowanie

**Proces deployu w Portainer z Git repository:**

1. ✅ **Portainer pobiera pliki z Git** (docker-compose.yml, config files)
2. ✅ **Portainer parsuje i waliduje** konfigurację
3. ✅ **Portainer tworzy infrastrukturę** (networks, volumes)
4. ✅ **Portainer automatycznie ściąga obrazy Docker** z rejestrów
5. ✅ **Portainer tworzy Docker Swarm services** w odpowiedniej kolejności
6. ✅ **Docker Swarm uruchamia kontenery** z healthchecks
7. ✅ **Serwisy inicjalizują się** (Grafana provisioning, Prometheus scraping)
8. ✅ **Stack jest gotowy** - wszystkie serwisy działają

**Przy aktualizacji:**
- Portainer pobiera zmiany z Git
- Porównuje konfigurację
- Wykonuje rolling update (zero-downtime)
- Zachowuje dane w volumes

