"""
Spark ETL: clean, join, and aggregate retail sales into feature-ready tables.

Uses local PySpark when Java is available; falls back to an equivalent pandas
path only if Spark cannot start (so demos still work). The Spark code path is
the primary, interview-defendable implementation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "retail_sales.csv"
PROCESSED = ROOT / "data" / "processed"


def _spark_etl() -> dict:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    spark = (
        SparkSession.builder.master("local[*]")
        .appName("ForecastIQ-ETL")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.driver.memory", "2g")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    df = spark.read.option("header", True).option("inferSchema", True).csv(str(RAW))
    df = (
        df.withColumn("date", F.to_date("date"))
        .filter(F.col("units_sold") >= 0)
        .filter(F.col("sku_id").isNotNull())
        .dropDuplicates(["date", "store_id", "sku_id"])
    )

    daily = (
        df.groupBy("date", "store_id", "sku_id", "sku_name", "category", "unit_price")
        .agg(
            F.sum("units_sold").alias("units_sold"),
            F.sum("revenue").alias("revenue"),
            F.max("promo_flag").alias("promo_flag"),
        )
        .orderBy("sku_id", "date")
    )

    w = Window.partitionBy("sku_id").orderBy("date")
    featured = (
        daily.withColumn("lag_1", F.lag("units_sold", 1).over(w))
        .withColumn("lag_7", F.lag("units_sold", 7).over(w))
        .withColumn(
            "roll_7_mean",
            F.avg("units_sold").over(w.rowsBetween(-6, 0)),
        )
        .withColumn(
            "roll_7_std",
            F.stddev("units_sold").over(w.rowsBetween(-6, 0)),
        )
        .withColumn("dow", F.dayofweek("date"))
        .withColumn("weekofyear", F.weekofyear("date"))
        .na.fill({"lag_1": 0, "lag_7": 0, "roll_7_std": 0})
    )

    sku_summary = (
        featured.groupBy("sku_id", "sku_name", "category", "unit_price")
        .agg(
            F.sum("units_sold").alias("total_units"),
            F.sum("revenue").alias("total_revenue"),
            F.avg("units_sold").alias("avg_daily_units"),
            F.max("date").alias("last_date"),
        )
        .orderBy(F.desc("total_revenue"))
    )

    PROCESSED.mkdir(parents=True, exist_ok=True)
    featured_pd = featured.toPandas()
    summary_pd = sku_summary.toPandas()
    featured_pd.to_csv(PROCESSED / "daily_features.csv", index=False)
    summary_pd.to_csv(PROCESSED / "sku_summary.csv", index=False)

    meta = {
        "engine": "pyspark",
        "rows_in": df.count(),
        "feature_rows": len(featured_pd),
        "skus": int(summary_pd.shape[0]),
        "date_min": str(featured_pd["date"].min()),
        "date_max": str(featured_pd["date"].max()),
    }
    spark.stop()
    return meta


def _pandas_etl() -> dict:
    """Equivalent transforms if JVM/Spark is unavailable on the machine."""
    df = pd.read_csv(RAW, parse_dates=["date"])
    df = df[df["units_sold"] >= 0].dropna(subset=["sku_id"])
    df = df.drop_duplicates(["date", "store_id", "sku_id"])

    daily = (
        df.groupby(
            ["date", "store_id", "sku_id", "sku_name", "category", "unit_price"],
            as_index=False,
        )
        .agg(
            units_sold=("units_sold", "sum"),
            revenue=("revenue", "sum"),
            promo_flag=("promo_flag", "max"),
        )
        .sort_values(["sku_id", "date"])
    )

    parts = []
    for _, g in daily.groupby("sku_id", sort=False):
        g = g.copy()
        g["lag_1"] = g["units_sold"].shift(1).fillna(0)
        g["lag_7"] = g["units_sold"].shift(7).fillna(0)
        g["roll_7_mean"] = g["units_sold"].rolling(7, min_periods=1).mean()
        g["roll_7_std"] = g["units_sold"].rolling(7, min_periods=1).std().fillna(0)
        g["dow"] = g["date"].dt.dayofweek + 1
        g["weekofyear"] = g["date"].dt.isocalendar().week.astype(int)
        parts.append(g)
    featured = pd.concat(parts, ignore_index=True)

    summary = (
        featured.groupby(["sku_id", "sku_name", "category", "unit_price"], as_index=False)
        .agg(
            total_units=("units_sold", "sum"),
            total_revenue=("revenue", "sum"),
            avg_daily_units=("units_sold", "mean"),
            last_date=("date", "max"),
        )
        .sort_values("total_revenue", ascending=False)
    )

    PROCESSED.mkdir(parents=True, exist_ok=True)
    featured.to_csv(PROCESSED / "daily_features.csv", index=False)
    summary.to_csv(PROCESSED / "sku_summary.csv", index=False)

    return {
        "engine": "pandas-fallback",
        "rows_in": int(len(df)),
        "feature_rows": int(len(featured)),
        "skus": int(len(summary)),
        "date_min": str(featured["date"].min().date()),
        "date_max": str(featured["date"].max().date()),
    }


def run() -> dict:
    if not RAW.exists():
        from pipelines.generate_sample_data import main as gen

        gen()

    # Prefer Spark; allow FORCE_PANDAS_ETL=1 for constrained hosts
    if os.getenv("FORCE_PANDAS_ETL", "").lower() in {"1", "true", "yes"}:
        meta = _pandas_etl()
    else:
        try:
            meta = _spark_etl()
        except Exception as exc:  # noqa: BLE001
            print(f"Spark unavailable ({exc}); using pandas-equivalent ETL.")
            meta = _pandas_etl()

    meta_path = PROCESSED / "etl_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    run()
