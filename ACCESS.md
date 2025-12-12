# 🔗 Dostęp do aplikacji monitoringowych

## Adresy URL aplikacji

Wszystkie aplikacje są dostępne przez Traefik z HTTPS (jeśli Traefik ma skonfigurowany SSL) lub bezpośrednio przez porty.

### Przez Traefik (z prefiksami ścieżek)

**Bazowy adres:** `https://<MONITORING_HOST>` lub `http://<MONITORING_HOST>`

Gdzie `<MONITORING_HOST>` to wartość zmiennej środowiskowej `MONITORING_HOST` (domyślnie: `57.129.41.248`)

#### 1. 📊 Grafana - Dashboardy i wizualizacje
- **URL:** `https://<MONITORING_HOST>/grafana`
- **Port bezpośredni:** `http://<MONITORING_HOST>:3000`
- **Login:** `admin` (lub wartość z `GRAFANA_ADMIN_USER`)
- **Hasło:** Wartość z `GRAFANA_ADMIN_PASSWORD`
- **Funkcje:** 
  - Tworzenie dashboardów
  - Wizualizacja metryk z Prometheus
  - Przeglądanie logów z Loki
  - Zarządzanie alertami

#### 2. 📈 Prometheus - Metryki i alerty
- **URL:** `https://<MONITORING_HOST>/prometheus`
- **Port bezpośredni:** `http://<MONITORING_HOST>:9090`
- **Funkcje:**
  - Przeglądanie metryk
  - Wykonywanie zapytań PromQL
  - Sprawdzanie alertów
  - Konfiguracja targetów

#### 3. 🚨 Alertmanager - Zarządzanie alertami
- **URL:** `https://<MONITORING_HOST>/alertmanager`
- **Port bezpośredni:** `http://<MONITORING_HOST>:9093`
- **Funkcje:**
  - Przeglądanie aktywnych alertów
  - Konfiguracja routingu alertów
  - Zarządzanie grupami alertów
  - Historia alertów

#### 4. 📝 Loki - Logi
- **URL:** `https://<MONITORING_HOST>/loki`
- **Port bezpośredni:** `http://<MONITORING_HOST>:3100`
- **Funkcje:**
  - Przeglądanie logów kontenerów
  - Wyszukiwanie w logach
  - Filtrowanie logów

#### 5. ✅ Uptime Kuma - Monitoring dostępności
- **URL:** `https://<MONITORING_HOST>/uptime-kuma`
- **Port bezpośredni:** `http://<MONITORING_HOST>:3001`
- **Login:** Ustaw przy pierwszym uruchomieniu (domyślnie: `admin`)
- **Hasło:** Ustaw przy pierwszym uruchomieniu
- **Funkcje:**
  - Monitoring dostępności serwisów
  - Status stron HTTP/HTTPS
  - Powiadomienia o awariach
  - Historia dostępności

#### 6. 💾 Duplicati - Backup
- **URL:** `https://<MONITORING_HOST>/duplicati`
- **Port bezpośredni:** `http://<MONITORING_HOST>:8200`
- **Login:** Ustaw przy pierwszym uruchomieniu
- **Hasło:** Ustaw przy pierwszym uruchomieniu
- **Funkcje:**
  - Tworzenie backupów volumes Docker
  - Planowanie automatycznych backupów
  - Przywracanie danych

### Bezpośrednie porty (jeśli Traefik nie jest skonfigurowany)

Jeśli nie masz Traefik lub chcesz uzyskać dostęp bezpośrednio:

- **Grafana:** `http://<MONITORING_HOST>:3000`
- **Prometheus:** `http://<MONITORING_HOST>:9090`
- **Alertmanager:** `http://<MONITORING_HOST>:9093`
- **Loki:** `http://<MONITORING_HOST>:3100`
- **Uptime Kuma:** `http://<MONITORING_HOST>:3001`
- **Duplicati:** `http://<MONITORING_HOST>:8200`
- **Telegram Webhook:** `http://<MONITORING_HOST>:8088` (tylko healthcheck)
- **Blackbox Exporter:** `http://<MONITORING_HOST>:9115` (tylko metryki)
- **cAdvisor:** `http://<MONITORING_HOST>:8081` (tylko metryki)
- **Node Exporter:** `http://<MONITORING_HOST>:9100` (tylko metryki)

## 🔐 Pierwsze uruchomienie

### Grafana
1. Otwórz `https://<MONITORING_HOST>/grafana`
2. Zaloguj się używając:
   - **Username:** `admin` (lub wartość z `GRAFANA_ADMIN_USER`)
   - **Password:** Wartość z `GRAFANA_ADMIN_PASSWORD`
3. Przy pierwszym logowaniu możesz zostać poproszony o zmianę hasła

### Uptime Kuma
1. Otwórz `https://<MONITORING_HOST>/uptime-kuma`
2. Przy pierwszym uruchomieniu utwórz konto administratora
3. Ustaw username i password
4. Serwis `uptime-kuma-init` automatycznie utworzy monitory z pliku YAML

### Duplicati
1. Otwórz `https://<MONITORING_HOST>/duplicati`
2. Przy pierwszym uruchomieniu utwórz konto administratora
3. Skonfiguruj backup jobs dla volumes:
   - `/source/prometheus`
   - `/source/grafana`
   - `/source/loki`
   - `/source/uptime-kuma`
   - `/source/alertmanager`

## 📋 Przykładowe adresy (dla MONITORING_HOST=57.129.41.248)

- Grafana: `https://57.129.41.248/grafana` lub `http://57.129.41.248:3000`
- Prometheus: `https://57.129.41.248/prometheus` lub `http://57.129.41.248:9090`
- Alertmanager: `https://57.129.41.248/alertmanager` lub `http://57.129.41.248:9093`
- Loki: `https://57.129.41.248/loki` lub `http://57.129.41.248:3100`
- Uptime Kuma: `https://57.129.41.248/uptime-kuma` lub `http://57.129.41.248:3001`
- Duplicati: `https://57.129.41.248/duplicati` lub `http://57.129.41.248:8200`

## 🔍 Sprawdzenie statusu serwisów

```bash
# Sprawdź status wszystkich serwisów
docker service ls | grep monitoring

# Sprawdź logi konkretnego serwisu
docker service logs monitoring_grafana
docker service logs monitoring_prometheus
docker service logs monitoring_uptime-kuma
```

## ⚠️ Uwagi

- Jeśli używasz HTTPS przez Traefik, upewnij się, że Traefik ma skonfigurowany SSL certificate
- Jeśli nie masz Traefik, użyj bezpośrednich portów
- Wszystkie aplikacje są dostępne tylko z sieci, w której działa Docker Swarm (domyślnie lokalnie)
- Aby udostępnić aplikacje publicznie, skonfiguruj Traefik lub użyj port forwarding

