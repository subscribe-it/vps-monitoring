FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY scripts/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy script (will be overridden by Docker Swarm Configs, but needed for build)
COPY scripts/uptime-kuma-init.py /app/uptime-kuma-init.py

# Create config directory (will be populated by Docker Swarm Configs)
RUN mkdir -p /app/config/uptime-kuma

# Run script
CMD ["python3", "uptime-kuma-init.py"]

