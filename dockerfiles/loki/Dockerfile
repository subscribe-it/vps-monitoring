# Loki z konfiguracją i regułami alertów logowych (ruler).
FROM grafana/loki:3.6.17
USER root
COPY config/loki/loki-config.yaml /etc/loki/loki-config.yaml
# Reguły muszą leżeć w podkatalogu tenanta: przy auth_enabled=false tenant to
# "fake". Bez tego ruler startuje, ale ma ZERO reguł (cicha awaria alertów logowych).
COPY config/loki/rules /etc/loki/rules
USER 10001
