FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/arbitrage/

# Environment
ENV ARB_DRY_RUN=true
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose healthcheck port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

CMD ["python", "-m", "arbitrage.main"]
