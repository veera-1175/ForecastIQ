"""LangChain insight agent over forecast KPIs and SKU predictions."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data" / "artifacts" / "forecast_bundle.json"


def load_bundle() -> dict[str, Any]:
    if not BUNDLE.exists():
        from pipelines.train_forecast import train

        train()
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


def _tool_catalog(bundle: dict[str, Any]) -> str:
    lines = [
        f"Overall MAE: {bundle['summary']['overall_mae']}",
        f"Overall RMSE: {bundle['summary']['overall_rmse']}",
        f"Horizon: {bundle['summary']['horizon_days']} days",
        "",
        "SKU forecasts:",
    ]
    for f in bundle["forecasts"]:
        lines.append(
            f"- {f['sku_name']} ({f['sku_id']}, {f['category']}): "
            f"next-{bundle['summary']['horizon_days']}d units={f['forecast_total_units']}, "
            f"revenue=₹{f['forecast_revenue']}, MAE={f['mae']}, insight={f['insight']}"
        )
    return "\n".join(lines)


def _rule_based_answer(question: str, bundle: dict[str, Any]) -> str:
    q = question.lower()
    forecasts = bundle["forecasts"]
    if not forecasts:
        return "No forecast data is available yet. Run the training pipeline first."

    if any(k in q for k in ["restock", "stock", "inventory", "reorder"]):
        ranked = sorted(forecasts, key=lambda x: x["forecast_total_units"], reverse=True)[:3]
        bullets = "\n".join(
            f"• **{r['sku_name']}** — ~{r['forecast_total_units']:.0f} units over 14 days ({r['insight']})"
            for r in ranked
        )
        return (
            "Based on the 14-day TensorFlow forecast, prioritize restock for:\n\n"
            f"{bullets}\n\n"
            f"Model average error (MAE) is **{bundle['summary']['overall_mae']} units/day** — "
            "use that as a safety buffer when setting reorder points."
        )

    if any(k in q for k in ["revenue", "money", "sales", "rupee", "inr", "top sku", "highest"]):
        top = forecasts[0]
        total = sum(f["forecast_revenue"] for f in forecasts)
        return (
            f"**{top['sku_name']}** is the top revenue SKU in the next 14 days "
            f"(~₹{top['forecast_revenue']:,.2f}). "
            f"All-SKU forecast revenue is ~₹{total:,.2f}.\n\n{top['insight']}"
        )

    if any(k in q for k in ["mae", "rmse", "accuracy", "error", "reliable"]):
        return (
            f"Holdout evaluation: **MAE {bundle['summary']['overall_mae']}**, "
            f"**RMSE {bundle['summary']['overall_rmse']}** (units/day, averaged across SKUs). "
            "Lower is better. Treat forecasts as planning signals, not guarantees — "
            "especially around promo weeks."
        )

    if "dairy" in q or "beverage" in q or "bakery" in q or "grocery" in q or "snack" in q:
        for cat in ["Dairy", "Beverages", "Bakery", "Grocery", "Snacks"]:
            if cat.lower() in q:
                subset = [f for f in forecasts if f["category"] == cat]
                if not subset:
                    return f"No SKUs found in category {cat}."
                total_u = sum(f["forecast_total_units"] for f in subset)
                names = ", ".join(f["sku_name"] for f in subset)
                return (
                    f"**{cat}** outlook: ~{total_u:.0f} units across {len(subset)} SKUs "
                    f"({names}) in the next 14 days."
                )

    # default brief
    top3 = forecasts[:3]
    lines = "\n".join(
        f"• {f['sku_name']}: {f['forecast_total_units']:.0f} units · ₹{f['forecast_revenue']:,.0f} · {f['insight']}"
        for f in top3
    )
    return (
        "Here’s a concise planning brief from the Spark → TensorFlow → LangChain pipeline:\n\n"
        f"{lines}\n\n"
        "Ask about restock priorities, category outlook, revenue leaders, or model error (MAE/RMSE)."
    )


def answer_question(question: str) -> dict[str, Any]:
    bundle = load_bundle()
    catalog = _tool_catalog(bundle)

    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    used_llm = False
    answer = None
    backend = "rules"

    try:
        if provider == "openai" and openai_key:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key, temperature=0.2)
            messages = [
                SystemMessage(
                    content=(
                        "You are ForecastIQ, a retail demand insight agent for business users. "
                        "Answer clearly with short paragraphs and bullets. Use only the forecast context. "
                        "Explain what numbers mean for inventory and revenue decisions. "
                        "If unsure, say what is unknown.\n\nCONTEXT:\n" + catalog
                    )
                ),
                HumanMessage(content=question),
            ]
            answer = llm.invoke(messages).content
            used_llm = True
            backend = "langchain-openai"
        elif groq_key:
            from langchain_groq import ChatGroq
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = ChatGroq(model="llama-3.1-8b-instant", api_key=groq_key, temperature=0.2)
            messages = [
                SystemMessage(
                    content=(
                        "You are ForecastIQ, a retail demand insight agent for business users. "
                        "Answer clearly with short paragraphs and bullets. Use only the forecast context. "
                        "Explain what numbers mean for inventory and revenue decisions.\n\nCONTEXT:\n"
                        + catalog
                    )
                ),
                HumanMessage(content=question),
            ]
            answer = llm.invoke(messages).content
            used_llm = True
            backend = "langchain-groq"
    except Exception as exc:  # noqa: BLE001
        answer = _rule_based_answer(question, bundle) + f"\n\n_(LLM fallback: {exc})_"
        backend = "rules-fallback"

    if not answer:
        answer = _rule_based_answer(question, bundle)

    return {
        "question": question,
        "answer": answer,
        "backend": backend,
        "used_llm": used_llm,
        "suggestions": [
            "Which SKUs should we restock first?",
            "What is the 14-day revenue outlook?",
            "How accurate is the model (MAE/RMSE)?",
            "How is Dairy category demand looking?",
        ],
    }
