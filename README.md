# ForecastIQ

Retail **Demand Forecasting & Insight Agent** — Spark/pandas ETL → TensorFlow forecast → LangChain Q&A, with CSV upload.

## Live demo
**https://forecastiq-4019.onrender.com**

Use **Use demo CSV** on the page (or upload your own). Free Render instances may cold-start in ~30–60s on first open.

Static mirror: https://veera-1175.github.io/ForecastIQ/

Repo: https://github.com/veera-1175/ForecastIQ

## Demo walkthrough
1. Open the live demo
2. Click **Use demo CSV** (or upload your own)
3. Wait ~1 min for ETL + forecast
4. Ask the insight agent in plain English

## Local
```bash
pip install -r requirements.txt
python -m pipelines.generate_sample_data
python -m pipelines.spark_etl
python -m pipelines.train_forecast
uvicorn app.main:app --reload --port 8000
```

## Deploy
Docker on Render (`Dockerfile` + `FORCE_PANDAS_ETL=1` + `GROQ_API_KEY`).
