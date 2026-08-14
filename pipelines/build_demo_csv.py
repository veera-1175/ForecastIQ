"""Build a ready-to-upload demo CSV with enough history for forecasting."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "templates" / "demo_upload.csv"

SKUS = [
    ("SKU-D001", "Filter Coffee 250g", "Beverages", 380.0),
    ("SKU-D002", "Toned Milk 1L", "Dairy", 56.0),
    ("SKU-D003", "Atta 5kg", "Grocery", 280.0),
    ("SKU-D004", "Banana Chips", "Snacks", 45.0),
]


def build(days: int = 90, seed: int = 7) -> Path:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-03-01", periods=days, freq="D")
    rows = []
    for sku_id, name, category, price in SKUS:
        base = rng.integers(30, 80)
        for i, day in enumerate(dates):
            seasonal = 1 + 0.15 * np.sin(2 * np.pi * i / 28)
            weekly = 1.12 if day.dayofweek >= 5 else 0.95
            noise = rng.normal(1.0, 0.07)
            promo = 1.3 if rng.random() < 0.06 else 1.0
            units = max(0, int(base * seasonal * weekly * noise * promo))
            rows.append(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "store_id": "STR-DEMO-01",
                    "sku_id": sku_id,
                    "sku_name": name,
                    "category": category,
                    "unit_price": price,
                    "units_sold": units,
                    "revenue": round(units * price, 2),
                    "promo_flag": int(promo > 1),
                }
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
