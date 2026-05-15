FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DASHBOARD_PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --system --create-home zenith \
    && mkdir -p /app/data \
    && chown -R zenith:zenith /app

USER zenith

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=8)" \
    || exit 1

# combo_main.py — единая точка входа (funding + grid + momentum)
CMD ["python", "combo_main.py"]
