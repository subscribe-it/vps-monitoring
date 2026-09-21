# Promtail z konfiguracją zbierania logów.
FROM grafana/promtail:3.6.11
USER root
# Ścieżka musi się zgadzać z `-config.file=` w docker-compose.yml
COPY config/promtail/promtail-config.yaml /etc/promtail/config.yml
USER 0
