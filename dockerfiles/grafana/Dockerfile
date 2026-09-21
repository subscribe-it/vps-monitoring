# Grafana z provisioningiem datasource'ów i dashboardami jako kod.
FROM grafana/grafana:13.2.2
USER root
COPY config/grafana/provisioning /etc/grafana/provisioning
COPY config/grafana/dashboards /var/lib/grafana/dashboards
USER 472
