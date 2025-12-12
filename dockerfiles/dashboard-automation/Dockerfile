FROM python:3.11-slim

WORKDIR /app

# Install wget for healthcheck
RUN apt-get update && apt-get install -y wget procps && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY scripts/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy script (will be overridden by Docker Swarm Configs, but needed for build)
COPY scripts/dashboard-automation.py /app/dashboard-automation.py

# Create templates directory (will be populated by Docker Swarm Configs)
RUN mkdir -p /app/templates

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=30s \
  CMD pgrep -f dashboard-automation.py || exit 1

# Run script
CMD ["python3", "dashboard-automation.py"]

