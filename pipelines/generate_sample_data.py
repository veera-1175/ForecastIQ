"""Generate synthetic retail daily sales for ForecastIQ demos."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"


SKUS = [
    ("SKU-1001", "Organic Milk 1L", "Dairy", 2.49),
    ("SKU-1002", "Whole Wheat Bread", "Bakery", 1.99),
    ("SKU-1003", "Arabica Coffee 250g", "Beverages", 8.50),
    ("SKU-1004", "Basmati Rice 5kg", "Grocery", 12.99),
    ("SKU-1005", "Greek Yogurt Pack", "Dairy", 4.25),
    ("SKU-1006", "Sparkling Water 12pk", "Beverages", 6.75),
    ("SKU-1007", "Dark Chocolate Bar", "Snacks", 3.10),
    ("SKU-1008", "Olive Oil 1L", "Grocery", 9.80),
]


def generate(days: int = 180, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2025-01-01")
    dates = pd.date_range(start, periods=days, freq="D")
    rows: list[dict] = []

    for sku_id, name, category, price in SKUS:
        base = rng.integers(25, 90)
        season_amp = rng.uniform(0.08, 0.22)
        weekly_amp = rng.uniform(0.05, 0.18)
        trend = rng.uniform(-0.02, 0.05)

        for i, day in enumerate(dates):
            seasonal = 1 + season_amp * np.sin(2 * np.pi * i / 30)
            weekly = 1 + weekly_amp * (0.6 if day.dayofweek >= 5 else -0.1)
            growth = 1 + trend * (i / max(days, 1))
            noise = rng.normal(1.0, 0.08)
            promo = 1.35 if rng.random() < 0.07 else 1.0
            units = max(0, int(base * seasonal * weekly * growth * noise * promo))
            rows.append(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "store_id": "STR-BLR-01",
                    "sku_id": sku_id,
                    "sku_name": name,
                    "category": category,
                    "unit_price": price,
                    "units_sold": units,
                    "revenue": round(units * price, 2),
                    "promo_flag": int(promo > 1),
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df = generate(days=args.days)
    out = RAW_DIR / "retail_sales.csv"
    df.to_csv(out, index=False)
    print(f"Wrote {len(df):,} rows -> {out}")


if __name__ == "__main__":
    main()
