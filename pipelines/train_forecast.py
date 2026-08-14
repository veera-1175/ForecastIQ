"""Train a TensorFlow demand forecaster and persist metrics + predictions."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler
import tensorflow as tf
from tensorflow import keras

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "processed" / "daily_features.csv"
MODELS = ROOT / "models"
ARTIFACTS = ROOT / "data" / "artifacts"
WINDOW = 14
HORIZON = 14


def _build_windows(values: np.ndarray, window: int = WINDOW) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for i in range(len(values) - window):
        xs.append(values[i : i + window])
        ys.append(values[i + window])
    return np.array(xs), np.array(ys)


def _make_model(window: int = WINDOW) -> keras.Model:
    model = keras.Sequential(
        [
            keras.layers.Input(shape=(window, 1)),
            keras.layers.LSTM(64, return_sequences=False),
            keras.layers.Dense(32, activation="relu"),
            keras.layers.Dense(1),
        ]
    )
    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss="mse", metrics=["mae"])
    return model


def _forecast_sku(series: np.ndarray, model: keras.Model, scaler: StandardScaler) -> list[float]:
    hist = series.copy()
    preds: list[float] = []
    for _ in range(HORIZON):
        window = hist[-WINDOW:]
        x = scaler.transform(window.reshape(-1, 1)).reshape(1, WINDOW, 1)
        yhat = float(model.predict(x, verbose=0)[0][0])
        # invert scale for a single value
        y_inv = float(scaler.inverse_transform(np.array([[yhat]]))[0][0])
        y_inv = max(0.0, y_inv)
        preds.append(round(y_inv, 2))
        hist = np.append(hist, y_inv)
    return preds


def train() -> dict:
    if not FEATURES.exists():
        from pipelines.spark_etl import run as etl

        etl()

    df = pd.read_csv(FEATURES, parse_dates=["date"]).sort_values(["sku_id", "date"])
    MODELS.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    # Train one global model on pooled windows (defendable + lighter for demo)
    all_x, all_y = [], []
    sku_series: dict[str, np.ndarray] = {}
    meta_rows = []

    for sku_id, g in df.groupby("sku_id"):
        units = g["units_sold"].astype(float).values
        sku_series[sku_id] = units
        if len(units) <= WINDOW + 5:
            continue
        scaler = StandardScaler()
        scaled = scaler.fit_transform(units.reshape(-1, 1)).ravel()
        x, y = _build_windows(scaled)
        all_x.append(x)
        all_y.append(y)
        meta_rows.append(
            {
                "sku_id": sku_id,
                "sku_name": g["sku_name"].iloc[0],
                "category": g["category"].iloc[0],
                "unit_price": float(g["unit_price"].iloc[0]),
                "scaler": scaler,
                "last_date": str(g["date"].max().date()),
                "history": [
                    {"date": d.strftime("%Y-%m-%d"), "units": float(u)}
                    for d, u in zip(g["date"], g["units_sold"])
                ],
            }
        )

    X = np.concatenate(all_x).reshape(-1, WINDOW, 1)
    y = np.concatenate(all_y)

    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    tf.random.set_seed(42)
    model = _make_model()
    model.fit(
        X_train,
        y_train,
        validation_data=(X_test, y_test),
        epochs=12,
        batch_size=64,
        verbose=0,
    )

    y_pred = model.predict(X_test, verbose=0).ravel()
    # Metrics in scaled space are not business-friendly; report on inverse using identity approx via MAE on scaled * mean scale
    # Better: evaluate per-SKU in original units with recursive 1-step on holdout tail
    per_sku_metrics = []
    forecasts = []

    for row in meta_rows:
        sku_id = row["sku_id"]
        units = sku_series[sku_id]
        scaler: StandardScaler = row["scaler"]
        if len(units) <= WINDOW + 10:
            continue
        hold = 14
        train_u = units[:-hold]
        actual = units[-hold:]
        # quick 1-model fine use: recursive from train_u
        # Train tiny adapter: use global model + sku scaler
        preds = []
        hist = train_u.copy()
        for _ in range(hold):
            w = hist[-WINDOW:]
            x = scaler.transform(w.reshape(-1, 1)).reshape(1, WINDOW, 1)
            yhat_s = float(model.predict(x, verbose=0)[0][0])
            yhat = float(scaler.inverse_transform(np.array([[yhat_s]]))[0][0])
            yhat = max(0.0, yhat)
            preds.append(yhat)
            hist = np.append(hist, yhat)
        mae = float(mean_absolute_error(actual, preds))
        rmse = float(np.sqrt(mean_squared_error(actual, preds)))
        per_sku_metrics.append(
            {
                "sku_id": sku_id,
                "sku_name": row["sku_name"],
                "category": row["category"],
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "avg_daily_units": round(float(np.mean(units)), 2),
            }
        )

        future = _forecast_sku(units, model, scaler)
        last = pd.Timestamp(row["last_date"])
        future_dates = [(last + pd.Timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(HORIZON)]
        forecasts.append(
            {
                "sku_id": sku_id,
                "sku_name": row["sku_name"],
                "category": row["category"],
                "unit_price": row["unit_price"],
                "history": row["history"][-60:],
                "forecast": [
                    {"date": d, "units": u} for d, u in zip(future_dates, future)
                ],
                "forecast_total_units": round(sum(future), 2),
                "forecast_revenue": round(sum(future) * row["unit_price"], 2),
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "insight": _insight(row["sku_name"], future, mae),
            }
        )

    overall_mae = round(float(np.mean([m["mae"] for m in per_sku_metrics])), 2)
    overall_rmse = round(float(np.mean([m["rmse"] for m in per_sku_metrics])), 2)

    model.save(MODELS / "demand_lstm.keras")
    joblib.dump({r["sku_id"]: r["scaler"] for r in meta_rows}, MODELS / "scalers.joblib")

    summary = {
        "model": "TensorFlow LSTM",
        "window": WINDOW,
        "horizon_days": HORIZON,
        "train_windows": int(len(X_train)),
        "test_windows": int(len(X_test)),
        "overall_mae": overall_mae,
        "overall_rmse": overall_rmse,
        "skus": len(forecasts),
        "scaled_test_mae": round(float(mean_absolute_error(y_test, y_pred)), 4),
    }

    payload = {
        "summary": summary,
        "sku_metrics": per_sku_metrics,
        "forecasts": sorted(forecasts, key=lambda x: x["forecast_revenue"], reverse=True),
        "kpis": _kpis(forecasts, summary),
        "pipeline": {
            "steps": [
                {"id": "spark", "label": "Spark ETL", "status": "done", "detail": "Cleaned & aggregated sales into feature tables"},
                {"id": "model", "label": "TensorFlow Forecast", "status": "done", "detail": f"LSTM trained · MAE {overall_mae} · RMSE {overall_rmse}"},
                {"id": "agent", "label": "Insight Agent", "status": "ready", "detail": "Ask business questions in plain English"},
            ]
        },
    }

    (ARTIFACTS / "forecast_bundle.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (ARTIFACTS / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return payload


def _insight(name: str, future: list[float], mae: float) -> str:
    first = np.mean(future[:7])
    second = np.mean(future[7:])
    delta = (second - first) / max(first, 1e-6)
    if delta > 0.08:
        trend = "rising demand over the next two weeks"
    elif delta < -0.08:
        trend = "softening demand — consider promo or stock reduction"
    else:
        trend = "stable demand"
    return f"{name}: {trend}. Model typical error ≈ {mae:.1f} units/day."


def _kpis(forecasts: list[dict], summary: dict) -> list[dict]:
    total_units = sum(f["forecast_total_units"] for f in forecasts)
    total_rev = sum(f["forecast_revenue"] for f in forecasts)
    top = forecasts[0] if forecasts else None
    return [
        {
            "label": "14-day forecast units",
            "value": f"{total_units:,.0f}",
            "hint": "Total predicted units across all SKUs",
        },
        {
            "label": "14-day forecast revenue",
            "value": f"${total_rev:,.0f}",
            "hint": "Units × unit price (list price assumption)",
        },
        {
            "label": "Model MAE",
            "value": str(summary["overall_mae"]),
            "hint": "Mean absolute error on holdout days (lower is better)",
        },
        {
            "label": "Top revenue SKU",
            "value": top["sku_name"] if top else "—",
            "hint": "Highest predicted revenue in the forecast window",
        },
    ]


if __name__ == "__main__":
    train()
