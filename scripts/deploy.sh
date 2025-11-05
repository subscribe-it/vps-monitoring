#!/bin/bash

# VPS Monitoring Stack Deployment Script
# Usage: ./deploy.sh [deploy|update|rollback|status]

set -e

STACK_NAME="monitoring"
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Warning: .env file not found. Using defaults from .env.example${NC}"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}Created .env from .env.example. Please edit it with your configuration.${NC}"
    fi
fi

# Check if docker-compose.yml exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}Error: $COMPOSE_FILE not found!${NC}"
    exit 1
fi

# Check if Docker Swarm is initialized
if ! docker info | grep -q "Swarm: active"; then
    echo -e "${RED}Error: Docker Swarm is not initialized!${NC}"
    echo "Run: docker swarm init"
    exit 1
fi

# Check if traefik-public network exists
if ! docker network ls | grep -q "traefik-public"; then
    echo -e "${YELLOW}Warning: traefik-public network not found. Creating it...${NC}"
    docker network create --driver overlay traefik-public
    echo -e "${GREEN}Created traefik-public network${NC}"
fi

deploy() {
    echo -e "${GREEN}Deploying $STACK_NAME stack...${NC}"
    docker stack deploy -c "$COMPOSE_FILE" "$STACK_NAME"
    echo -e "${GREEN}Stack deployed successfully!${NC}"
    echo ""
    echo "Waiting for services to start..."
    sleep 10
    status
}

update() {
    echo -e "${GREEN}Updating $STACK_NAME stack...${NC}"
    docker stack deploy -c "$COMPOSE_FILE" "$STACK_NAME"
    echo -e "${GREEN}Stack updated successfully!${NC}"
    echo ""
    echo "Waiting for services to update..."
    sleep 10
    status
}

rollback() {
    echo -e "${YELLOW}Rollback functionality requires manual intervention${NC}"
    echo "To rollback:"
    echo "1. Check previous configuration: git log docker-compose.yml"
    echo "2. Restore previous version: git checkout <commit> -- docker-compose.yml"
    echo "3. Redeploy: docker stack deploy -c $COMPOSE_FILE $STACK_NAME"
}

status() {
    echo -e "${GREEN}Status of $STACK_NAME stack:${NC}"
    echo ""
    docker stack services "$STACK_NAME"
    echo ""
    echo -e "${GREEN}Service details:${NC}"
    docker service ls | grep "$STACK_NAME"
}

logs() {
    SERVICE=$2
    if [ -z "$SERVICE" ]; then
        echo -e "${YELLOW}Available services:${NC}"
        docker service ls | grep "$STACK_NAME" | awk '{print $2}' | sed 's/.*\///'
        echo ""
        echo "Usage: $0 logs <service-name>"
        echo "Example: $0 logs prometheus"
    else
        echo -e "${GREEN}Logs for $STACK_NAME_$SERVICE:${NC}"
        docker service logs -f "$STACK_NAME"_"$SERVICE"
    fi
}

case "$1" in
    deploy)
        deploy
        ;;
    update)
        update
        ;;
    rollback)
        rollback
        ;;
    status)
        status
        ;;
    logs)
        logs "$@"
        ;;
    *)
        echo "Usage: $0 {deploy|update|rollback|status|logs [service]}"
        echo ""
        echo "Commands:"
        echo "  deploy   - Deploy the monitoring stack"
        echo "  update   - Update the monitoring stack"
        echo "  rollback - Show rollback instructions"
        echo "  status   - Show stack status"
        echo "  logs     - Show logs for a service (requires service name)"
        exit 1
        ;;
esac


