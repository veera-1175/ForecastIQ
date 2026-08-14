# ForecastIQ

Retail **Demand Forecasting & Insight Agent** — Spark ETL → TensorFlow forecast → LangChain Q&A, with a business-user dashboard.

**Live demo:** *(added after deploy)*

## Interview walkthrough (90 seconds)

1. **Data** — synthetic retail daily sales (8 SKUs, ~180 days)
2. **Spark ETL** — clean/dedupe, daily aggregates, lag & rolling features → `data/processed/`
3. **TensorFlow** — LSTM demand model, holdout MAE/RMSE, 14-day forecast bundle
4. **LangChain agent** — plain-English answers grounded in forecast KPIs (Groq/OpenAI, with rule fallback)
5. **UI** — KPI cards, history vs forecast chart, “what this means” copy, SKU board, chat

## Quick start (local)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt

python -m pipelines.generate_sample_data
python -m pipelines.spark_etl
python -m pipelines.train_forecast

uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000

Optional `.env`:

```
GROQ_API_KEY=...
LLM_PROVIDER=groq
```

Without an API key, the agent uses a deterministic rules engine over the same forecast bundle (still demoable).

## Deploy

Demo image uses **precomputed artifacts** (no Spark/TF on the free host). Rebuild artifacts locally before push if data/model changes.

```bash
# Render: connect this repo, Docker runtime, or
render.yaml
```

## Resume alignment

| Claim | Where |
|---|---|
| Spark ETL | `pipelines/spark_etl.py` |
| TensorFlow + MAE/RMSE | `pipelines/train_forecast.py` |
| LangChain insight agent | `app/agent.py` |
| pandas / scikit-learn | features, scalers, metrics |
