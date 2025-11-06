# Troubleshooting - VPS Monitoring Stack

## Problem: "config not found" errors

### Symptomy

Błędy typu:
```
service telegram-webhook: config not found: telegram_webhook_script
service prometheus: config not found: prometheus_config
```

### Przyczyna

Docker Swarm Configs nie zostały utworzone w Portainer przed deployem stacku.

### Rozwiązanie

**1. Sprawdź czy wszystkie Docker Configs są utworzone:**

W Portainer → **Configs** → sprawdź czy wszystkie 14 configs istnieją:
- `prometheus_config`
- `prometheus_alerts_system`
- `prometheus_alerts_http`
- `prometheus_alerts_monitoring`
- `prometheus_alerts_prometheus`
- `loki_config`
- `promtail_config`
- `alertmanager_config`
- `blackbox_config`
- `grafana_datasources`
- `grafana_dashboards`
- `telegram_webhook_script`
- `telegram_webhook_requirements`
- `dashboard_automation_script`

**2. Jeśli brakuje configs (NAJWAŻNIEJSZE!):**

**Musisz utworzyć wszystkie 14 configs przed deployem stacku!**

**Szybka instrukcja:**

1. W Portainer → **Configs** → **Add config**
2. Dla każdego pliku z listy poniżej:
   - **Name**: (dokładnie jak w tabeli - ważne!)
   - **Content**: Skopiuj zawartość pliku z repozytorium GitHub
   - Kliknij **Create the config**

**Lista wszystkich 14 configs:**

| Config Name | Plik źródłowy w repo |
|------------|---------------------|
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

**⚠️ WAŻNE:**
- Nazwy configs muszą być **dokładnie** takie same jak w tabeli (case-sensitive!)
- Jeśli brakuje choć jednego config, stack nie wystartuje
- Po utworzeniu wszystkich configs, zaktualizuj stack w Portainer

**Alternatywnie przez CLI (jeśli masz SSH):**
```bash
git clone <repository-url>
cd vps-monitoring
./scripts/create-configs.sh create
```

Szczegóły: [DEPLOYMENT.md](DEPLOYMENT.md) - sekcja "Tworzenie Docker Swarm Configs"

## Problem: "rejected" services lub "bind source path does not exist"

### Symptomy

Błędy typu:
```
invalid mount config for type "bind": bind source path does not exist: /data/compose/25/config/promtail/promtail-config.yaml
```

### Przyczyna

Portainer próbuje użyć bind mounts z względnymi ścieżkami, ale stack używa Docker Swarm Configs zamiast bind mounts.

### Rozwiązanie

**1. Sprawdź czy wszystkie Docker Configs są utworzone:**

W Portainer → **Configs** → sprawdź czy wszystkie 14 configs istnieją:

**3. Zaktualizuj stack w Portainer:**

Jeśli stack już istnieje i używa starej wersji z bind mounts:

1. W Portainer → **Stacks** → **monitoring** → **Editor**
2. Kliknij **Pull and redeploy** (lub **Update the stack**)
3. To powinno pobrać najnowszą wersję `docker-compose.yml` z Git repository

**4. Jeśli problem nadal występuje:**

Sprawdź czy Portainer pobrał najnowszą wersję z Git:

1. W Portainer → **Stacks** → **monitoring** → **Editor**
2. Sprawdź czy w docker-compose.yml są:
   - Sekcja `configs:` z `external: true`
   - Serwisy używają `configs:` zamiast `volumes:` dla plików konfiguracyjnych
3. Jeśli nie, kliknij **Pull and redeploy**

**5. Alternatywnie - usuń i utwórz stack na nowo:**

⚠️ **UWAGA:** To usunie wszystkie dane (volumes)! Tylko jeśli masz backup.

```bash
# W Portainer: Stacks → monitoring → Remove
# Następnie utwórz stack na nowo z Git repository
```

## Problem: Templates directory nie działa

### Symptomy

Dashboard automation działa, ale nie ma preloaded templates.

### Przyczyna

Bind mount dla templates directory jest wykomentowany (opcjonalny).

### Rozwiązanie

**Opcja 1: Użyj templates bez bind mount**

Dashboard automation będzie działać bez preloaded templates - tworzy dashboardy dynamicznie.

**Opcja 2: Włącz bind mount dla templates**

1. W Portainer → **Stacks** → **monitoring** → **Editor**
2. Znajdź serwisy `grafana` i `dashboard-automation`
3. Znajdź wykomentowane linie z templates:
   ```yaml
   # - /data/compose/25/config/grafana/provisioning/dashboards/templates:/...
   ```
4. Odkomentuj i zmień ścieżkę na właściwą:
   - W Portainer, sprawdź gdzie jest sklonowane repo (zwykle `/data/compose/ID/`)
   - Zmień `25` na właściwy ID twojego stacku
5. Kliknij **Update the stack**

**Jak znaleźć ścieżkę repo w Portainer:**

1. W Portainer → **Stacks** → **monitoring** → **Editor**
2. Na górze powinna być informacja o lokalizacji repo
3. Albo użyj SSH i sprawdź:
   ```bash
   ls -la /data/compose/
   # Znajdź katalog z twoim stackiem
   ```

## Problem: Serwis nie startuje

### Sprawdź logi

W Portainer → **Stacks** → **monitoring** → kliknij na serwis → **Logs**

### Najczęstsze przyczyny

1. **Brak Docker Configs** - utwórz wszystkie configs przed deployem
2. **Brak network `traefik-public`** - utwórz network: `docker network create --driver overlay traefik-public`
3. **Brak volumes** - volumes są tworzone automatycznie przy pierwszym deployu
4. **Resource limits** - sprawdź czy masz wystarczające zasoby (RAM, CPU)

## Problem: Grafana nie pokazuje dashboardów

### Sprawdź

1. W Grafana → **Configuration** → **Data Sources**
   - Powinny być: Prometheus i Loki (utworzone automatycznie)
2. W Grafana → **Dashboards** → **Browse**
   - Powinny być preloaded dashboardy
3. Sprawdź logi `dashboard-automation`:
   ```bash
   docker service logs monitoring_dashboard-automation
   ```

### Rozwiązanie

1. Sprawdź czy `grafana_datasources` i `grafana_dashboards` configs są utworzone
2. Sprawdź czy serwis `dashboard-automation` działa
3. Sprawdź logi Prometheus - czy wykrywa kontenery z labelami `app.name` i `app.type`

## Problem: Prometheus nie wykrywa kontenerów

### Sprawdź

1. W Prometheus → **Status** → **Targets**
   - Powinny być wszystkie aktywne targets
2. Sprawdź czy kontenery mają label `prometheus.io/scrape=true`

### Rozwiązanie

Dodaj labels do kontenerów które chcesz monitorować:

```yaml
labels:
  - "prometheus.io/scrape=true"
  - "prometheus.io/port=9090"
  - "prometheus.io/path=/metrics"
  - "app.name=my-service"
  - "app.type=api"
```

## Problem: Alerty nie działają

### Sprawdź

1. W Prometheus → **Alerts** - czy są aktywne alerty
2. W Alertmanager → **Alerts** - czy alerty są wysyłane
3. Sprawdź logi `telegram-webhook`:
   ```bash
   docker service logs monitoring_telegram-webhook
   ```

### Rozwiązanie

1. Sprawdź czy `alertmanager_config` jest utworzony
2. Sprawdź czy zmienne `TELEGRAM_BOT_TOKEN` i `TELEGRAM_CHAT_ID` są ustawione
3. Sprawdź czy `telegram-webhook` serwis działa

## Problem: Porty są zajęte

### Symptomy

```
port '8088' is already in use by service '...'
```

### Rozwiązanie

1. Sprawdź które serwisy używają portów:
   ```bash
   docker service ls
   ```
2. Zmień port w docker-compose.yml lub usuń konfliktujący serwis

## Przydatne komendy

### Sprawdź status wszystkich serwisów

```bash
docker service ls | grep monitoring
```

### Sprawdź logi serwisu

```bash
docker service logs monitoring_prometheus --follow
docker service logs monitoring_grafana --follow
```

### Sprawdź czy configs są utworzone

```bash
docker config ls | grep -E "prometheus|loki|grafana|alertmanager"
```

### Sprawdź czy volumes istnieją

```bash
docker volume ls | grep monitoring
```

### Sprawdź czy networks istnieją

```bash
docker network ls | grep -E "monitoring|traefik-public"
```

### Restart serwisu

```bash
docker service update --force monitoring_prometheus
```

### Usuń i utwórz config na nowo

```bash
# Usuń
docker config rm prometheus_config

# Utwórz na nowo
docker config create prometheus_config config/prometheus/prometheus.yml
```


