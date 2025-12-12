#!/bin/bash

# Helper script to display all configs needed for Portainer deployment
# This script shows the content of each config file that needs to be created in Portainer

set -e

REPO_DIR="${REPO_DIR:-$(pwd)}"

echo "=========================================="
echo "Portainer Configs Helper"
echo "=========================================="
echo ""
echo "Utwórz te configs w Portainerze przed wdrożeniem stacku:"
echo ""
echo "Portainer → Configs → Add config"
echo ""

# List of all configs with their source files
declare -A configs=(
    ["prometheus_config"]="config/prometheus/prometheus.yml"
    ["prometheus_alerts_system"]="config/prometheus/alerts/system.yml"
    ["prometheus_alerts_http"]="config/prometheus/alerts/http.yml"
    ["prometheus_alerts_monitoring"]="config/prometheus/alerts/monitoring.yml"
    ["prometheus_alerts_prometheus"]="config/prometheus/alerts/prometheus.yml"
    ["loki_config"]="config/loki/loki-config.yaml"
    ["promtail_config"]="config/promtail/promtail-config.yaml"
    ["alertmanager_config"]="config/alertmanager/alertmanager.yml"
    ["blackbox_config"]="config/blackbox/blackbox.yml"
    ["grafana_datasources"]="config/grafana/provisioning/datasources/datasources.yml"
    ["grafana_dashboards"]="config/grafana/provisioning/dashboards/dashboards.yml"
    ["telegram_webhook_script"]="scripts/telegram-webhook.py"
    ["telegram_webhook_requirements"]="scripts/requirements.txt"
    ["dashboard_automation_script"]="scripts/dashboard-automation.py"
    ["dashboard_template_wordpress"]="config/grafana/provisioning/dashboards/templates/wordpress.json"
    ["dashboard_template_generic_app"]="config/grafana/provisioning/dashboards/templates/generic-app.json"
    ["dashboard_template_database"]="config/grafana/provisioning/dashboards/templates/database.json"
    ["uptime_kuma_config"]="config/uptime-kuma/uptime-kuma-config.yaml"
    ["uptime_kuma_init_script"]="scripts/uptime-kuma-init.py"
)

counter=1
for config_name in "${!configs[@]}"; do
    file_path="${configs[$config_name]}"
    full_path="$REPO_DIR/$file_path"
    
    if [ -f "$full_path" ]; then
        echo "$counter. Config Name: $config_name"
        echo "   File: $file_path"
        echo "   Full path: $full_path"
        echo ""
        counter=$((counter + 1))
    else
        echo "⚠️  WARNING: File not found: $full_path" >&2
    fi
done

echo "=========================================="
echo "WAŻNE:"
echo "1. Utwórz wszystkie configs w Portainerze PRZED wdrożeniem stacku"
echo "2. Odśwież stronę Portainera (F5) po utworzeniu configs"
echo "3. Sprawdź czy wszystkie 19 configs są widoczne w Portainer → Configs"
echo "4. Dopiero potem wdróż stack"
echo "=========================================="

