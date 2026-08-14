# ForecastIQ

Retail **Demand Forecasting & Insight Agent** — Spark/pandas ETL → TensorFlow forecast → LangChain Q&A, with CSV upload.

## Live demo (full app — upload + Groq)
**https://annoying-dealmaker-gerbil.ngrok-free.dev**

> Click **Visit Site** if ngrok shows a warning page. Use **Use demo CSV** on the page.

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

## Deploy (Render)
Connect this repo in Render (Docker). Set `GROQ_API_KEY` and `FORCE_PANDAS_ETL=1`.
