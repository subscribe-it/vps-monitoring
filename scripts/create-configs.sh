#!/bin/bash

# Script to create Docker Swarm Configs from repository files
# Usage: ./scripts/create-configs.sh [create|delete|list]

set -e

STACK_NAME="monitoring"
REPO_DIR="${REPO_DIR:-$(pwd)}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if Docker Swarm is initialized
if ! docker info | grep -q "Swarm: active"; then
    echo -e "${RED}Error: Docker Swarm is not initialized!${NC}"
    echo "Run: docker swarm init"
    exit 1
fi

create_configs() {
    echo -e "${GREEN}Creating Docker Swarm Configs for monitoring stack...${NC}"
    echo ""
    
    # Check if configs directory exists
    if [ ! -d "$REPO_DIR/config" ]; then
        echo -e "${RED}Error: config directory not found at $REPO_DIR/config${NC}"
        exit 1
    fi
    
    # Prometheus config
    echo -e "${YELLOW}Creating prometheus_config...${NC}"
    docker config create prometheus_config "$REPO_DIR/config/prometheus/prometheus.yml" 2>/dev/null || \
        (echo "  ⚠️  prometheus_config already exists, updating..." && \
         docker config rm prometheus_config && \
         docker config create prometheus_config "$REPO_DIR/config/prometheus/prometheus.yml")
    
    # Prometheus alerts
    echo -e "${YELLOW}Creating prometheus_alerts_system...${NC}"
    docker config create prometheus_alerts_system "$REPO_DIR/config/prometheus/alerts/system.yml" 2>/dev/null || \
        (docker config rm prometheus_alerts_system 2>/dev/null; \
         docker config create prometheus_alerts_system "$REPO_DIR/config/prometheus/alerts/system.yml")
    
    echo -e "${YELLOW}Creating prometheus_alerts_http...${NC}"
    docker config create prometheus_alerts_http "$REPO_DIR/config/prometheus/alerts/http.yml" 2>/dev/null || \
        (docker config rm prometheus_alerts_http 2>/dev/null; \
         docker config create prometheus_alerts_http "$REPO_DIR/config/prometheus/alerts/http.yml")
    
    echo -e "${YELLOW}Creating prometheus_alerts_monitoring...${NC}"
    docker config create prometheus_alerts_monitoring "$REPO_DIR/config/prometheus/alerts/monitoring.yml" 2>/dev/null || \
        (docker config rm prometheus_alerts_monitoring 2>/dev/null; \
         docker config create prometheus_alerts_monitoring "$REPO_DIR/config/prometheus/alerts/monitoring.yml")
    
    echo -e "${YELLOW}Creating prometheus_alerts_prometheus...${NC}"
    docker config create prometheus_alerts_prometheus "$REPO_DIR/config/prometheus/alerts/prometheus.yml" 2>/dev/null || \
        (docker config rm prometheus_alerts_prometheus 2>/dev/null; \
         docker config create prometheus_alerts_prometheus "$REPO_DIR/config/prometheus/alerts/prometheus.yml")
    
    # Loki config
    echo -e "${YELLOW}Creating loki_config...${NC}"
    docker config create loki_config "$REPO_DIR/config/loki/loki-config.yaml" 2>/dev/null || \
        (docker config rm loki_config 2>/dev/null; \
         docker config create loki_config "$REPO_DIR/config/loki/loki-config.yaml")
    
    # Promtail config
    echo -e "${YELLOW}Creating promtail_config...${NC}"
    docker config create promtail_config "$REPO_DIR/config/promtail/promtail-config.yaml" 2>/dev/null || \
        (docker config rm promtail_config 2>/dev/null; \
         docker config create promtail_config "$REPO_DIR/config/promtail/promtail-config.yaml")
    
    # Alertmanager config
    echo -e "${YELLOW}Creating alertmanager_config...${NC}"
    docker config create alertmanager_config "$REPO_DIR/config/alertmanager/alertmanager.yml" 2>/dev/null || \
        (docker config rm alertmanager_config 2>/dev/null; \
         docker config create alertmanager_config "$REPO_DIR/config/alertmanager/alertmanager.yml")
    
    # Blackbox config
    echo -e "${YELLOW}Creating blackbox_config...${NC}"
    docker config create blackbox_config "$REPO_DIR/config/blackbox/blackbox.yml" 2>/dev/null || \
        (docker config rm blackbox_config 2>/dev/null; \
         docker config create blackbox_config "$REPO_DIR/config/blackbox/blackbox.yml")
    
    # Grafana datasources
    echo -e "${YELLOW}Creating grafana_datasources...${NC}"
    docker config create grafana_datasources "$REPO_DIR/config/grafana/provisioning/datasources/datasources.yml" 2>/dev/null || \
        (docker config rm grafana_datasources 2>/dev/null; \
         docker config create grafana_datasources "$REPO_DIR/config/grafana/provisioning/datasources/datasources.yml")
    
    # Grafana dashboards
    echo -e "${YELLOW}Creating grafana_dashboards...${NC}"
    docker config create grafana_dashboards "$REPO_DIR/config/grafana/provisioning/dashboards/dashboards.yml" 2>/dev/null || \
        (docker config rm grafana_dashboards 2>/dev/null; \
         docker config create grafana_dashboards "$REPO_DIR/config/grafana/provisioning/dashboards/dashboards.yml")
    
    # Telegram webhook script
    echo -e "${YELLOW}Creating telegram_webhook_script...${NC}"
    docker config create telegram_webhook_script "$REPO_DIR/scripts/telegram-webhook.py" 2>/dev/null || \
        (docker config rm telegram_webhook_script 2>/dev/null; \
         docker config create telegram_webhook_script "$REPO_DIR/scripts/telegram-webhook.py")
    
    # Telegram webhook requirements
    echo -e "${YELLOW}Creating telegram_webhook_requirements...${NC}"
    docker config create telegram_webhook_requirements "$REPO_DIR/scripts/requirements.txt" 2>/dev/null || \
        (docker config rm telegram_webhook_requirements 2>/dev/null; \
         docker config create telegram_webhook_requirements "$REPO_DIR/scripts/requirements.txt")
    
    # Dashboard automation script
    echo -e "${YELLOW}Creating dashboard_automation_script...${NC}"
    docker config create dashboard_automation_script "$REPO_DIR/scripts/dashboard-automation.py" 2>/dev/null || \
        (docker config rm dashboard_automation_script 2>/dev/null; \
         docker config create dashboard_automation_script "$REPO_DIR/scripts/dashboard-automation.py")
    
    echo ""
    echo -e "${GREEN}✅ All Docker Configs created successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Deploy the stack in Portainer (or use: docker stack deploy -c docker-compose.yml monitoring)"
    echo "2. If you update config files, run this script again to update the configs"
}

delete_configs() {
    echo -e "${YELLOW}Deleting Docker Swarm Configs...${NC}"
    echo ""
    
    configs=(
        "prometheus_config"
        "prometheus_alerts_system"
        "prometheus_alerts_http"
        "prometheus_alerts_monitoring"
        "prometheus_alerts_prometheus"
        "loki_config"
        "promtail_config"
        "alertmanager_config"
        "blackbox_config"
        "grafana_datasources"
        "grafana_dashboards"
        "telegram_webhook_script"
        "telegram_webhook_requirements"
        "dashboard_automation_script"
    )
    
    for config in "${configs[@]}"; do
        if docker config ls | grep -q "$config"; then
            echo -e "${YELLOW}Deleting $config...${NC}"
            docker config rm "$config" 2>/dev/null || true
        else
            echo -e "  ⚠️  $config does not exist"
        fi
    done
    
    echo ""
    echo -e "${GREEN}✅ Configs deletion completed${NC}"
}

list_configs() {
    echo -e "${GREEN}Docker Swarm Configs for monitoring stack:${NC}"
    echo ""
    docker config ls | grep -E "NAME|prometheus|alerts|loki|promtail|alertmanager|blackbox|grafana|telegram|dashboard" || echo "No configs found"
}

case "${1:-create}" in
    create)
        create_configs
        ;;
    delete)
        delete_configs
        ;;
    list)
        list_configs
        ;;
    *)
        echo "Usage: $0 [create|delete|list]"
        echo ""
        echo "Commands:"
        echo "  create  - Create all Docker Swarm Configs from repository files (default)"
        echo "  delete  - Delete all Docker Swarm Configs"
        echo "  list    - List all Docker Swarm Configs"
        exit 1
        ;;
esac

