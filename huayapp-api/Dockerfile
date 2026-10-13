FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DATABASE_PATH=/data/lottery.db

WORKDIR /app

COPY huayapp-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && playwright install --with-deps chromium

# Build from the repository root so the verified scraper package is included.
COPY huayapp_scraper /app/huayapp_scraper
COPY huayapp-api/app.py /app/app.py

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
