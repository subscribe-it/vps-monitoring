# Grafana z provisioningiem datasource'ów i dashboardami jako kod.
FROM grafana/grafana:13.2.2
USER root
COPY config/grafana/provisioning /etc/grafana/provisioning
# Dashboardy NIE mogą leżeć w /var/lib/grafana: to wolumen (grafana_data_v2),
# do którego Docker kopiuje zawartość obrazu TYLKO przy pierwszym starcie.
# Późniejsze zmiany w obrazie były przez ten wolumen zasłaniane — nowy dashboard
# istniał w obrazie, ale Grafana go nie widziała (zmierzone 2026-09-22).
COPY config/grafana/dashboards /etc/grafana/dashboards
USER 472
