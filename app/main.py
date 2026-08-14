from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.agent import answer_question, load_bundle

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="ForecastIQ", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://veera-1175.github.io",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_origin_regex=r"https://.*\.ngrok-free\.(app|dev)|https://.*\.onrender\.com",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))


class ChatIn(BaseModel):
    question: str = Field(min_length=3, max_length=800)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    bundle = load_bundle()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "bundle_json": json.dumps(bundle),
            "summary": bundle["summary"],
            "kpis": bundle["kpis"],
            "pipeline": bundle["pipeline"]["steps"],
            "forecasts": bundle["forecasts"],
        },
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "ForecastIQ",
        "groq": bool(os.getenv("GROQ_API_KEY", "").strip()),
    }


@app.get("/api/forecast")
def forecast():
    return load_bundle()


@app.post("/api/chat")
def chat(body: ChatIn):
    return answer_question(body.question.strip())


@app.get("/api/skus/{sku_id}")
def sku_detail(sku_id: str):
    bundle = load_bundle()
    for f in bundle["forecasts"]:
        if f["sku_id"] == sku_id:
            return f
    return JSONResponse({"error": "SKU not found"}, status_code=404)


def create_app() -> FastAPI:
    return app
