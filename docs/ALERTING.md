# System Alertów i Powiadomień

## Przegląd

System alertów VPS Monitoring używa Prometheus Alertmanager do wykrywania problemów i wysyłania powiadomień przez Telegram. System monitoruje:

- **Zużycie zasobów**: CPU, RAM, dysk
- **Błędy HTTP**: 4xx i 5xx
- **Dostępność serwisów**: status up/down
- **Zdrowie kontenerów**: brak odpowiedzi

## Komponenty

### Alertmanager

Alertmanager zarządza alertami z Prometheus:
- Grupowanie i deduplikacja alertów
- Routing do różnych kanałów powiadomień
- Silencing i inhibition rules
- Retry i timeout handling

### Telegram Webhook

Custom serwis `telegram-webhook`:
- Odbiera webhooks z Alertmanager
- Formatuje wiadomości w Markdown
- Wysyła do Telegram Bot API
- Obsługuje różne poziomy ważności (critical, warning)

### Alert Rules

Alert rules są zdefiniowane w `config/prometheus/alerts/`:
- `system.yml` - alerty systemowe (CPU, RAM, disk, service down)
- `http.yml` - alerty HTTP (4xx, 5xx errors)
- `prometheus.yml` - monitoring samego Prometheus

## Konfiguracja Telegram

### 1. Utworzenie Bota Telegram

1. Otwórz Telegram i znajdź [@BotFather](https://t.me/BotFather)
2. Wyślij `/newbot`
3. Podaj nazwę bota (np. "VPS Monitoring Bot")
4. Podaj username bota (np. "vps_monitoring_bot")
5. Skopiuj **token** bota (np. `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Uzyskanie Chat ID

**Dla czatu prywatnego:**
1. Napisz wiadomość do swojego bota
2. Otwórz w przeglądarce: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Znajdź `"chat":{"id":123456789}` w odpowiedzi
4. To jest Twój Chat ID

**Dla kanału/grupy:**
1. Dodaj bota do kanału/grupy
2. Uczyń bota administratorem kanału
3. Wyślij wiadomość do kanału
4. Sprawdź `getUpdates` API - znajdź ID kanału (ujemne dla kanałów)

### 3. Konfiguracja w Stacku

Dodaj zmienne środowiskowe do `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

Lub w Portainer:
- Environment Variables → Add:
  - `TELEGRAM_BOT_TOKEN` = `twój_token`
  - `TELEGRAM_CHAT_ID` = `twój_chat_id`

## Alerty

### System Alerts

#### HighCPUUsage
- **Wyzwalacz**: CPU usage > 90% przez 5 minut
- **Severity**: critical
- **Akcja**: Sprawdź co powoduje wysokie zużycie CPU

#### HighMemoryUsage
- **Wyzwalacz**: Memory usage > 90% limitu przez 5 minut
- **Severity**: critical
- **Akcja**: Sprawdź użycie pamięci, zwiększ limit lub zoptymalizuj aplikację

#### HighDiskUsage
- **Wyzwalacz**: Dostępne miejsce na dysku < 10% przez 5 minut
- **Severity**: critical
- **Akcja**: Zwolnij miejsce na dysku, usuń stare logi/backupy

#### ServiceDown
- **Wyzwalacz**: Serwis `up == 0` przez 1 minutę
- **Severity**: critical
- **Akcja**: Sprawdź dlaczego serwis padł, sprawdź logi

#### ContainerNotResponding
- **Wyzwalacz**: Kontener nie widziany przez 60 sekund
- **Severity**: critical
- **Akcja**: Sprawdź status kontenera, restart jeśli potrzebny

### HTTP Alerts

#### HighHTTP4xxErrors
- **Wyzwalacz**: Rate błędów 4xx > 10/sec przez 5 minut
- **Severity**: warning
- **Akcja**: Sprawdź błędne żądania, może być problem z konfiguracją

#### HighHTTP5xxErrors
- **Wyzwalacz**: Rate błędów 5xx > 5/sec przez 5 minut
- **Severity**: critical
- **Akcja**: Sprawdź logi serwera, może być problem z aplikacją

#### HighHTTPResponseTime
- **Wyzwalacz**: 95th percentile response time > 2 sekundy przez 5 minut
- **Severity**: warning
- **Akcja**: Sprawdź wydajność aplikacji, może być przeciążenie

### Prometheus Alerts

#### PrometheusTargetDown
- **Wyzwalacz**: Prometheus target down przez 5 minut
- **Severity**: critical
- **Akcja**: Sprawdź dlaczego target nie odpowiada

## Dostosowywanie Alertów

### Zmiana progu alertu

Edytuj odpowiedni plik w `config/prometheus/alerts/`:

```yaml
# Przykład: zmiana progu CPU z 90% na 80%
- alert: HighCPUUsage
  expr: |
    rate(container_cpu_usage_seconds_total[5m]) * 100 > 80  # Zmieniono z 90
  for: 5m
```

### Dodanie nowego alertu

Dodaj nową regułę do istniejącego pliku lub utwórz nowy:

```yaml
groups:
  - name: custom_alerts
    interval: 30s
    rules:
      - alert: MyCustomAlert
        expr: your_promql_query_here
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Custom alert summary"
          description: "Detailed description of the alert"
```

## Uptime Kuma Auto-Restart

Uptime Kuma może automatycznie restartować serwisy które padły. Konfiguracja:

**Uwaga**: Uptime Kuma nie ma wbudowanej funkcji auto-restart. Musisz skonfigurować webhook notification który wywoła API do restartowania serwisu.

### 1. Konfiguracja Monitora w Uptime Kuma

1. Otwórz Uptime Kuma: `https://<MONITORING_HOST>/uptime-kuma`
2. Dodaj nowy monitor dla serwisu:
   - **Type**: HTTP(s)
   - **URL**: URL serwisu do monitorowania
   - **Interval**: 60 sekund (domyślnie)
   - **Retries**: 2
   - **Timeout**: 10 sekund
3. W sekcji **Notifications** dodaj webhook notification
4. Skonfiguruj webhook do restartowania serwisu

### 2. Docker API Restart (dla Docker Swarm)

**Webhook URL:**
```
http://<docker-host>:2375/containers/<container-name>/restart
```

**Lub przez Portainer API:**
```
http://<portainer-host>:9000/api/endpoints/<endpoint-id>/docker/containers/<container-id>/restart
```

**Headers:**
```
X-API-Key: <portainer-api-key>
```

### 3. Przykładowa konfiguracja

**Notification w Uptime Kuma:**
- **Type**: Webhook
- **URL**: `http://portainer:9000/api/endpoints/1/docker/containers/{container_id}/restart`
- **Method**: POST
- **Headers**: `X-API-Key: <your-api-key>`
- **Body**: (pusty)

**Uwaga**: Uptime Kuma musi mieć dostęp do Docker API lub Portainer API.

### 4. Automatyczny Restart przez Custom Script

Alternatywnie, możesz użyć custom script który będzie restartował serwisy:

**Utwórz script `restart-service.sh`:**
```bash
#!/bin/bash
# restart-service.sh
SERVICE_NAME=$1
docker service update --force ${SERVICE_NAME}
```

**Skonfiguruj webhook w Uptime Kuma:**
- **Type**: Webhook
- **URL**: `http://localhost:2375/services/${service_name}/update?force=true`
- **Method**: POST
- **Body**: (pusty)

**Lub przez Portainer API:**
- **URL**: `http://portainer:9000/api/endpoints/1/docker/services/${service_id}/update`
- **Method**: POST
- **Headers**: `X-API-Key: <your-api-key>`
- **Body**: `{"force": true}`

### 5. Przykład: Restart Service Webhook

**Notification w Uptime Kuma dla serwisu `wordpress-production`:**

1. **W Portainer:**
   - Znajdź ID serwisu: `docker service ls | grep wordpress-production`
   - Utwórz API key w Portainer (Settings → API Keys)

2. **W Uptime Kuma:**
   - Dodaj monitor dla serwisu
   - W sekcji **Notifications** → **Add Notification**
   - **Type**: Webhook
   - **URL**: `http://portainer:9000/api/endpoints/1/docker/services/<service-id>/update`
   - **Method**: POST
   - **Headers**:
     ```
     X-API-Key: <your-portainer-api-key>
     Content-Type: application/json
     ```
   - **Body**:
     ```json
     {
       "force": true
     }
     ```

3. **Test:**
   - Zatrzymaj serwis ręcznie
   - Uptime Kuma wykryje problem
   - Webhook wywoła restart serwisu

## Testowanie Alertów

### Test Alertmanager

```bash
# Sprawdź status Alertmanager
curl http://localhost:9093/api/v2/status

# Wyślij test alert
curl -X POST http://localhost:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "service": "test"
    },
    "annotations": {
      "summary": "Test alert",
      "description": "This is a test alert"
    }
  }]'
```

### Test Telegram Webhook

```bash
# Sprawdź health
curl http://localhost:8080/

# Wyślij test webhook
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning",
        "service_name": "test-service"
      },
      "annotations": {
        "summary": "Test alert",
        "description": "This is a test alert"
      },
      "startsAt": "2025-01-01T00:00:00Z"
    }],
    "groupLabels": {
      "alertname": "TestAlert"
    },
    "commonLabels": {
      "severity": "warning"
    }
  }'
```

### Test Alert Rules

W Prometheus UI (`http://localhost:9090/alerts`):
- Sprawdź czy alerty są widoczne
- Sprawdź czy są w stanie "Pending" lub "Firing"
- Sprawdź czy są wysyłane do Alertmanager

## Troubleshooting

### Alerty nie są wysyłane do Telegram

1. **Sprawdź zmienne środowiskowe:**
   ```bash
   docker service logs monitoring_telegram-webhook | grep -i "credentials"
   ```

2. **Sprawdź logi telegram-webhook:**
   ```bash
   docker service logs monitoring_telegram-webhook
   ```

3. **Sprawdź token bota:**
   - Upewnij się że token jest poprawny
   - Sprawdź czy bot nie został usunięty/zablokowany

4. **Sprawdź Chat ID:**
   - Upewnij się że bot ma dostęp do czatu/kanału
   - Sprawdź czy bot jest administratorem (dla kanałów)

### Alerty nie są grupowane

- Sprawdź konfigurację `group_by` w `alertmanager.yml`
- Sprawdź czy labels są konsystentne między alertami

### Zbyt wiele alertów

- Zwiększ `repeat_interval` w `alertmanager.yml`
- Zwiększ `group_interval` dla grupowania
- Dodaj inhibition rules dla powiązanych alertów

### Alerty nie są rozwiązywane

- Sprawdź czy Prometheus wysyła resolved alerts
- Sprawdź `resolve_timeout` w `alertmanager.yml`
- Sprawdź logi Alertmanager

## Przykładowe Wiadomości Telegram

### Critical Alert

```
🚨 CRITICAL ALERT

HighCPUUsage

Status: FIRING
Severity: critical
Service: wordpress-production
Instance: wordpress-production.1.abc123
Container: wordpress-production

Summary: High CPU usage detected
Description: Container wordpress-production (wordpress) has CPU usage above 90% for more than 5 minutes. Current value: 95.2%

Started: 2025-01-01 12:00:00
```

### Warning Alert

```
⚠️ Warning Alert

HighHTTP4xxErrors

Status: FIRING
Severity: warning
Service: api-service
Instance: api-service:8080

Summary: High HTTP 4xx error rate
Description: Service api-service is experiencing high 4xx error rate: 12 errors/sec

Started: 2025-01-01 12:00:00
```

## Zobacz także

- [Prometheus Alerting Documentation](https://prometheus.io/docs/alerting/latest/overview/)
- [Alertmanager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Uptime Kuma Documentation](https://github.com/louislam/uptime-kuma)

