"""Validate uploaded retail CSVs and run Spark ETL → TensorFlow forecast."""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "retail_sales.csv"
RAW_BACKUP = ROOT / "data" / "raw" / "retail_sales.sample.csv"
UPLOADS = ROOT / "data" / "uploads"
TEMPLATE = ROOT / "data" / "templates" / "sales_template.csv"

REQUIRED = {"date", "sku_id", "units_sold"}
OPTIONAL_DEFAULTS = {
    "store_id": "STR-UPLOAD-01",
    "sku_name": None,  # filled from sku_id
    "category": "General",
    "unit_price": 100.0,
    "promo_flag": 0,
}


def ensure_sample_backup() -> None:
    if RAW.exists() and not RAW_BACKUP.exists():
        RAW_BACKUP.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAW, RAW_BACKUP)


def write_template() -> Path:
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    sample = pd.DataFrame(
        [
            {
                "date": "2025-01-01",
                "store_id": "STR-BLR-01",
                "sku_id": "SKU-1001",
                "sku_name": "Organic Milk 1L",
                "category": "Dairy",
                "unit_price": 68,
                "units_sold": 42,
                "revenue": 2856,
                "promo_flag": 0,
            },
            {
                "date": "2025-01-02",
                "store_id": "STR-BLR-01",
                "sku_id": "SKU-1001",
                "sku_name": "Organic Milk 1L",
                "category": "Dairy",
                "unit_price": 68,
                "units_sold": 38,
                "revenue": 2584,
                "promo_flag": 0,
            },
        ]
    )
    sample.to_csv(TEMPLATE, index=False)
    return TEMPLATE


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(sorted(missing))
            + ". Need at least: date, sku_id, units_sold."
        )

    for col, default in OPTIONAL_DEFAULTS.items():
        if col not in df.columns:
            if col == "sku_name":
                df[col] = df["sku_id"].astype(str)
            else:
                df[col] = default

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        raise ValueError("Some rows have invalid dates. Use YYYY-MM-DD.")

    df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(100.0)
    df["promo_flag"] = pd.to_numeric(df.get("promo_flag", 0), errors="coerce").fillna(0).astype(int)

    if df["units_sold"].isna().any():
        raise ValueError("units_sold must be numeric.")

    if "revenue" not in df.columns:
        df["revenue"] = (df["units_sold"] * df["unit_price"]).round(2)
    else:
        df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
        df["revenue"] = df["revenue"].fillna(df["units_sold"] * df["unit_price"]).round(2)

    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["sku_id"] = df["sku_id"].astype(str)
    df["sku_name"] = df["sku_name"].astype(str)
    df["category"] = df["category"].astype(str)
    df["store_id"] = df["store_id"].astype(str)

    # Need enough history for LSTM window
    by_sku = df.groupby("sku_id").size()
    weak = by_sku[by_sku < 30]
    if len(weak):
        raise ValueError(
            "Each SKU needs at least ~30 daily rows for forecasting. "
            f"Too short: {', '.join(weak.index.astype(str)[:5])}"
        )

    cols = [
        "date",
        "store_id",
        "sku_id",
        "sku_name",
        "category",
        "unit_price",
        "units_sold",
        "revenue",
        "promo_flag",
    ]
    return df[cols].sort_values(["sku_id", "date"])


def ingest_csv_bytes(content: bytes, filename: str = "upload.csv") -> dict[str, Any]:
    ensure_sample_backup()
    UPLOADS.mkdir(parents=True, exist_ok=True)

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read CSV: {exc}") from exc

    if df.empty:
        raise ValueError("CSV is empty.")

    clean = _normalize(df)
    stamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    saved_upload = UPLOADS / f"{stamp}_{Path(filename).name}"
    clean.to_csv(saved_upload, index=False)

    RAW.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(RAW, index=False)

    return {
        "rows": int(len(clean)),
        "skus": int(clean["sku_id"].nunique()),
        "date_min": str(clean["date"].min()),
        "date_max": str(clean["date"].max()),
        "saved_as": saved_upload.name,
    }


def run_pipeline(epochs: int = 8) -> dict[str, Any]:
    from pipelines.spark_etl import run as etl
    from pipelines.train_forecast import train

    etl_meta = etl()
    bundle = train(epochs=epochs)
    return {
        "etl": etl_meta,
        "summary": bundle["summary"],
        "source": "upload",
    }


def reset_to_sample() -> dict[str, Any]:
    ensure_sample_backup()
    if not RAW_BACKUP.exists():
        from pipelines.generate_sample_data import main as gen

        gen()
        ensure_sample_backup()
    shutil.copy2(RAW_BACKUP, RAW)
    return run_pipeline(epochs=8)
