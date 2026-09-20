FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose Web UI port
EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV WEBHOOK_PORT=8000
ENV WEBHOOK_HOST=0.0.0.0

# Start Web UI Dashboard and Bot Cluster
CMD ["python", "main.py", "dashboard"]
