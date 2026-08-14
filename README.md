# ForecastIQ

Retail **Demand Forecasting & Insight Agent** — Spark ETL → TensorFlow forecast → LangChain Q&A.

## Live demo
https://veera-1175.github.io/ForecastIQ/

Repo: https://github.com/veera-1175/ForecastIQ

## Local API
```bash
pip install -r requirements.txt
python -m pipelines.generate_sample_data
python -m pipelines.spark_etl
python -m pipelines.train_forecast
uvicorn app.main:app --reload --port 8000
```
