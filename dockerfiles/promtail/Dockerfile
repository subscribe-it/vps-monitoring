# Promtail z konfiguracją zbierania logów.
FROM grafana/promtail:3.6.11
USER root
COPY config/promtail/promtail-config.yaml /etc/promtail/promtail-config.yaml
USER 0
