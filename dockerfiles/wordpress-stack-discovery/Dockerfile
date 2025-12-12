FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY dockerfiles/wordpress-stack-discovery/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy script
COPY scripts/wordpress-stack-discovery.py .

CMD ["python3", "wordpress-stack-discovery.py"]

