from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.agent import answer_question, load_bundle
from pipelines.ingest import ingest_csv_bytes, reset_to_sample, run_pipeline, write_template

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="ForecastIQ", version="1.1.0")
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
        request,
        "index.html",
        {
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
        "upload": True,
    }


@app.get("/api/forecast")
def forecast():
    return load_bundle()


@app.get("/api/template.csv")
def template_csv():
    path = write_template()
    return FileResponse(path, media_type="text/csv", filename="forecastiq_sales_template.csv")


@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")
    content = await file.read()
    if len(content) > 8_000_000:
        raise HTTPException(status_code=400, detail="CSV too large (max ~8MB).")
    try:
        meta = ingest_csv_bytes(content, file.filename)
        result = run_pipeline(epochs=8)
        bundle = load_bundle()
        return {
            "ok": True,
            "message": "Upload processed: Spark ETL -> TensorFlow forecast refreshed.",
            "ingest": meta,
            "pipeline": result,
            "bundle": bundle,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc


@app.post("/api/reset-sample")
def reset_sample():
    try:
        result = reset_to_sample()
        return {"ok": True, "message": "Restored sample dataset and re-ran pipeline.", "pipeline": result, "bundle": load_bundle()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
