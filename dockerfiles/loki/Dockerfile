# Loki z konfiguracją i regułami alertów logowych (ruler).
FROM grafana/loki:3.6.17
USER root
COPY config/loki/loki-config.yaml /etc/loki/loki-config.yaml
COPY config/loki/rules /etc/loki/rules
USER 10001
