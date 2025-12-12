FROM python:3.11-slim

WORKDIR /app

# Install wget for healthcheck
RUN apt-get update && apt-get install -y wget && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY scripts/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy script (will be overridden by Docker Swarm Configs, but needed for build)
COPY scripts/telegram-webhook.py /app/telegram-webhook.py

# Expose port
EXPOSE 8088

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8088/health || exit 1

# Run script
CMD ["python3", "telegram-webhook.py"]

