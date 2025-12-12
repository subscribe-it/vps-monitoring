# 🚀 Szybki przewodnik wdrożenia do Portainera

## Krok po kroku

### 1. ✅ Przygotowanie Docker Swarm Configs (WAŻNE!)

**Musisz utworzyć wszystkie configs PRZED wdrożeniem stacku!**

**Opcja A: Przez Portainer UI**
1. Portainer → **Configs** → **Add config**
2. Dla każdego z 19 plików:
   - **Name**: (patrz lista poniżej)
   - **Content**: Skopiuj zawartość pliku z GitHub
   - Kliknij **Create the config**

**Opcja B: Przez skrypt (jeśli masz SSH)**
```bash
cd /run/media/dawid/Linux_Projekty/vps-monitoring
./scripts/create-configs.sh create
```

**Lista wszystkich 19 configs:**
1. `prometheus_config` → `config/prometheus/prometheus.yml`
2. `prometheus_alerts_system` → `config/prometheus/alerts/system.yml`
3. `prometheus_alerts_http` → `config/prometheus/alerts/http.yml`
4. `prometheus_alerts_monitoring` → `config/prometheus/alerts/monitoring.yml`
5. `prometheus_alerts_prometheus` → `config/prometheus/alerts/prometheus.yml`
6. `loki_config` → `config/loki/loki-config.yaml`
7. `promtail_config` → `config/promtail/promtail-config.yaml`
8. `alertmanager_config` → `config/alertmanager/alertmanager.yml`
9. `blackbox_config` → `config/blackbox/blackbox.yml`
10. `grafana_datasources` → `config/grafana/provisioning/datasources/datasources.yml`
11. `grafana_dashboards` → `config/grafana/provisioning/dashboards/dashboards.yml`
12. `telegram_webhook_script` → `scripts/telegram-webhook.py`
13. `telegram_webhook_requirements` → `scripts/requirements.txt`
14. `dashboard_automation_script` → `scripts/dashboard-automation.py`
15. `dashboard_template_wordpress` → `config/grafana/provisioning/dashboards/templates/wordpress.json`
16. `dashboard_template_generic_app` → `config/grafana/provisioning/dashboards/templates/generic-app.json`
17. `dashboard_template_database` → `config/grafana/provisioning/dashboards/templates/database.json`
18. `uptime_kuma_config` → `config/uptime-kuma/uptime-kuma-config.yaml`
19. `uptime_kuma_init_script` → `scripts/uptime-kuma-init.py`

### 2. ✅ Sprawdź sieć Traefik

1. Portainer → **Networks**
2. Sprawdź czy istnieje `traefik-public`
3. Jeśli nie - utwórz:
   - **Name**: `traefik-public`
   - **Driver**: `overlay`
   - **Scope**: `swarm`
   - **Attachable**: ✓ (zaznacz)

### 3. ✅ Wdrożenie stacku

**Opcja A: Z Git Repository (Rekomendowane)**

1. Portainer → **Stacks** → **Add stack**
2. **Name**: `monitoring`
3. **Build method**: Wybierz **Git repository**
4. **Repository URL**: `https://github.com/subscribe-it/vps-monitoring.git`
5. **Repository reference**: `main`
6. **Compose path**: `portainer-complete-stack.yml` (lub `docker-compose.yml` jeśli preferujesz)
7. **Auto-update**: (opcjonalnie) włącz dla automatycznych aktualizacji

**Opcja B: Web Editor (Rekomendowane dla portainer-complete-stack.yml)**

1. Portainer → **Stacks** → **Add stack**
2. **Name**: `monitoring`
3. **Build method**: Wybierz **Web editor**
4. Skopiuj zawartość `portainer-complete-stack.yml` z GitHub i wklej do edytora
   - Plik zawiera pełną dokumentację i komentarze dla Portainera
   - Alternatywnie możesz użyć `docker-compose.yml` (mniej dokumentacji)

### 4. ✅ Konfiguracja zmiennych środowiskowych

W Portainer Stack Editor, dodaj zmienne środowiskowe:

**Wymagane:**
- `GRAFANA_ADMIN_PASSWORD` = `twoje_bezpieczne_haslo` (min. 8 znaków)
- `MONITORING_HOST` = `57.129.41.248` (lub Twoja domena)
- `PROMETHEUS_RETENTION` = `720h` (30 dni)
- `LOKI_RETENTION_DAYS` = `720` (30 dni)

**Opcjonalne (ale zalecane):**
- `TELEGRAM_BOT_TOKEN` = `twój_token_z_botfather`
- `TELEGRAM_CHAT_ID` = `twój_chat_id`
- `GRAFANA_ADMIN_USER` = `admin`
- `CHECK_INTERVAL` = `60`
- `UPTIME_KUMA_USERNAME` = `admin`
- `UPTIME_KUMA_PASSWORD` = `hasło_ustawione_w_web_ui`

**Szybka kopia:** Wszystkie zmienne znajdziesz w pliku `env.portainer.example`

### 5. ✅ Deploy

1. Sprawdź czy wszystkie configs są utworzone (19 plików)
2. Sprawdź czy zmienne środowiskowe są dodane
3. Kliknij **Deploy the stack**
4. Poczekaj na uruchomienie wszystkich serwisów (1-2 minuty)

### 6. ✅ Weryfikacja

**Sprawdź status serwisów:**
```bash
docker service ls | grep monitoring
```

Powinno być 13 serwisów w stanie Running:
- monitoring_node-exporter
- monitoring_cadvisor
- monitoring_prometheus
- monitoring_loki
- monitoring_promtail
- monitoring_grafana
- monitoring_alertmanager
- monitoring_blackbox-exporter
- monitoring_telegram-webhook
- monitoring_dashboard-automation
- monitoring_uptime-kuma
- monitoring_duplicati
- monitoring_uptime-kuma-init

**Sprawdź logi (jeśli problemy):**
```bash
docker service logs monitoring_prometheus
docker service logs monitoring_grafana
docker service logs monitoring_telegram-webhook
```

**Dostęp do serwisów:**
- Grafana: `https://<MONITORING_HOST>/grafana`
- Prometheus: `https://<MONITORING_HOST>/prometheus`
- Alertmanager: `https://<MONITORING_HOST>/alertmanager`
- Uptime Kuma: `https://<MONITORING_HOST>/uptime-kuma`
- Duplicati: `https://<MONITORING_HOST>/duplicati`

### 7. ✅ Konfiguracja Uptime Kuma

1. Otwórz Uptime Kuma: `https://<MONITORING_HOST>/uptime-kuma`
2. Przy pierwszym uruchomieniu utwórz konto administratora
3. Serwis `uptime-kuma-init` automatycznie utworzy monitory z pliku YAML

### 8. ✅ Konfiguracja Duplicati (Backup)

1. Otwórz Duplicati: `https://<MONITORING_HOST>/duplicati`
2. Utwórz konto administratora
3. Utwórz backup job dla volumes:
   - `/source/prometheus`
   - `/source/grafana`
   - `/source/loki`
   - `/source/uptime-kuma`
   - `/source/alertmanager`

## ⚠️ Troubleshooting

**Problem: "config not found"**
- Sprawdź czy wszystkie 19 configs są utworzone w Portainer → Configs

**Problem: "network traefik-public not found"**
- Utwórz sieć `traefik-public` jako overlay network

**Problem: Serwisy nie startują**
- Sprawdź logi: `docker service logs monitoring_<nazwa-serwisu>`
- Sprawdź czy wszystkie zmienne środowiskowe są ustawione

**Problem: Obrazy Docker nie są pobierane**
- Obrazy z ghcr.io są publiczne i powinny być dostępne automatycznie
- Sprawdź czy masz dostęp do internetu z VPS

## 📚 Więcej informacji

- Pełna dokumentacja: [README.md](README.md)
- Szczegóły deploymentu: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- Konfiguracja: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

