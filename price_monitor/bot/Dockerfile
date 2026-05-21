FROM python:3.11-slim

WORKDIR /app

COPY bot/requirements.txt /tmp/bot-req.txt
COPY backend/requirements.txt /tmp/backend-req.txt
RUN pip install --no-cache-dir -r /tmp/bot-req.txt -r /tmp/backend-req.txt

COPY backend/app /app/app
COPY bot /app/bot

ENV PYTHONPATH=/app

CMD ["python", "-m", "bot.main"]
