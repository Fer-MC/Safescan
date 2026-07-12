"""
main.py — Aplicación FastAPI de VETLLA.

INICIO:
  1. Carga .env (ANTHROPIC_API_KEY)
  2. Arranca servidor FastAPI
  3. Sirve frontend + API

ENDPOINTS:
  GET  /              -> index.html (frontend)
  GET  /api/health    -> estado del servicio
  POST /api/analyze   -> analiza imagen con Claude Vision (param: lang)
  POST /api/report    -> genera informe Word (param: lang, incluye la foto)

CÓMO PROBAR LOCALMENTE:
  pip install -r requirements.txt
  echo "ANTHROPIC_API_KEY=sk-ant-xxxxxxx" > .env
  uvicorn main:app --reload --port 8000
"""

# CRÍTICO: Cargar .env PRIMERO, antes de importar config
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=str(env_file), override=False)
        print(f"✅ .env cargado desde {env_file}")
    else:
        print(f"⚠️  No encontré {env_file} — intentando variables de entorno del sistema")
except ImportError:
    print("⚠️  python-dotenv no instalado, intentando variables de entorno")

import json
import logging

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse

from config import settings, validate_runtime
from claude_service import analizar_imagen, AnalysisError
from report_service import generar_informe
from i18n import normalize_lang

logging.basicConfig(level=logging.INFO if not settings.debug else logging.DEBUG)
logger = logging.getLogger("vetlla")

app = FastAPI(title=settings.app_name)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.on_event("startup")
async def _startup():
    for problem in validate_runtime():
        logger.warning("CONFIG: %s", problem)


# --- Frontend --------------------------------------------------------------
@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# --- Salud -----------------------------------------------------------------
@app.get("/api/health")
async def health():
    problems = validate_runtime()
    return {"status": "ok" if not problems else "config_error", "issues": problems}


# --- Análisis --------------------------------------------------------------
@app.post("/api/analyze")
async def analyze(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form("es"),
):
    if file.content_type not in settings.allowed_mime:
        return JSONResponse(
            status_code=415,
            content={"error": "bad_type", "message": "Sube una imagen JPG, PNG o WEBP."},
        )

    image_bytes = await file.read()
    if not image_bytes:
        return JSONResponse(
            status_code=400,
            content={"error": "empty", "message": "El archivo está vacío."},
        )
    if len(image_bytes) > settings.max_image_bytes:
        return JSONResponse(
            status_code=413,
            content={"error": "too_large", "message": "La imagen supera el tamaño máximo (5 MB)."},
        )

    try:
        resultado = analizar_imagen(image_bytes, file.content_type, lang=normalize_lang(lang))
    except AnalysisError as exc:
        return JSONResponse(status_code=exc.status, content={"error": "analysis", "message": exc.message})
    except Exception:
        logger.exception("Error inesperado en /api/analyze")
        return JSONResponse(
            status_code=500,
            content={"error": "internal", "message": "Error inesperado al analizar la imagen."},
        )

    return JSONResponse(content={"data": resultado})


# --- Informe Word ----------------------------------------------------------
@app.post("/api/report")
async def report(
    payload: str = Form(...),
    empresa: str = Form(""),
    centro: str = Form(""),
    responsable: str = Form(""),
    lang: str = Form("es"),
    image: UploadFile | None = File(None),
):
    try:
        analisis = json.loads(payload)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "bad_payload", "message": "Datos de análisis inválidos."})

    image_bytes = None
    if image is not None:
        image_bytes = await image.read()
        if image_bytes and len(image_bytes) > settings.max_image_bytes:
            image_bytes = None  # ignora imágenes anómalas; el informe se genera igual

    lang = normalize_lang(lang)
    buffer = generar_informe(
        analisis,
        empresa=empresa.strip()[:120],
        centro=centro.strip()[:120],
        responsable=responsable.strip()[:120],
        lang=lang,
        image_bytes=image_bytes,
    )
    from i18n import report_strings
    filename = report_strings(lang)["filename"]
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
