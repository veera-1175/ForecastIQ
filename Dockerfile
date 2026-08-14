FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FORECASTIQ_DEMO_MODE=true
ENV FORCE_PANDAS_ETL=1
ENV LLM_PROVIDER=groq
ENV PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-live.txt .
RUN pip install --no-cache-dir -r requirements-live.txt

COPY app ./app
COPY pipelines ./pipelines
COPY data/artifacts ./data/artifacts
COPY data/processed ./data/processed
COPY data/raw ./data/raw
COPY data/templates ./data/templates
COPY models ./models

# Ensure writable dirs for uploads / retraining
RUN mkdir -p data/uploads data/raw data/processed data/artifacts models \
    && chmod -R a+rwX data models

EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
