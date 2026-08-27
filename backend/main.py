"""
main.py — Aplicación FastAPI de VETLLA.

RUTAS:
  GET  /                    -> landing.html (página comercial)
  GET  /app                 -> index.html (la app: foto -> análisis -> informe)
  GET  /aviso-legal         -> aviso-legal.html (placeholder, pendiente de contenido legal)
  GET  /privacidad          -> privacidad.html (placeholder, pendiente de contenido legal)
  GET  /faq                 -> faq.html
  GET  /como-funciona       -> como-funciona.html
  GET  /api/health          -> estado del servicio
  POST /api/analyze         -> analiza imagen con Claude Vision (param: lang)
  POST /api/report          -> genera informe Word (param: lang, email, incluye la foto)
  POST /api/checkout/easy   -> crea una Stripe Checkout Session para el bono Easy
  POST /api/stripe/webhook  -> recibe confirmaciones de pago de Stripe (carga créditos)

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
from usage_store import (
    is_valid_email, normalize_email,
    consume_if_allowed, refund_consumption, add_credits, mark_event_processed_if_new,
)
import stripe_service

logging.basicConfig(level=logging.INFO if not settings.debug else logging.DEBUG)
logger = logging.getLogger("vetlla")

app = FastAPI(title=settings.app_name)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# URL pública del sitio. Detrás del proxy de Railway el TLS se termina fuera
# del contenedor, así que request.base_url puede devolver http:// y Stripe
# rechazaría esa URL de retorno. Se configura explícitamente por entorno:
#   PUBLIC_BASE_URL=https://web-production-8ad37.up.railway.app
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")


def _public_base_url(request: Request) -> str:
    """URL pública fiable. Si no está configurada, deduce y fuerza https."""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://") and "localhost" not in base and "127.0.0.1" not in base:
        base = "https://" + base[len("http://"):]
    return base


@app.on_event("startup")
async def _startup():
    for problem in validate_runtime():
        logger.warning("CONFIG: %s", problem)


# --- Landing (página comercial) --------------------------------------------
@app.get("/")
async def landing():
    return FileResponse(FRONTEND_DIR / "landing.html")


# --- App (herramienta de análisis) -----------------------------------------
@app.get("/app")
async def app_page():
    return FileResponse(FRONTEND_DIR / "index.html")


# --- Páginas legales -------------------------------------------------------
# Placeholders: el contenido definitivo depende de datos fiscales pendientes.
@app.get("/aviso-legal")
async def aviso_legal():
    return FileResponse(FRONTEND_DIR / "aviso-legal.html")


@app.get("/privacidad")
async def privacidad():
    return FileResponse(FRONTEND_DIR / "privacidad.html")


# --- Páginas de contenido ----------------------------------------------
@app.get("/faq")
async def faq_page():
    return FileResponse(FRONTEND_DIR / "faq.html")


@app.get("/como-funciona")
async def como_funciona_page():
    return FileResponse(FRONTEND_DIR / "como-funciona.html")


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
    resp_zona: str = Form(""),
    supervisor: str = Form(""),
    lang: str = Form("es"),
    email: str = Form(...),
    image: UploadFile | None = File(None),
):
    # --- Gate de email + tope de 1 informe gratuito (whitelist exenta) ---
    email_norm = normalize_email(email)
    if not is_valid_email(email_norm):
        return JSONResponse(
            status_code=400,
            content={"error": "bad_email", "message": "Introduce un email válido para descargar el informe."},
        )

    try:
        analisis = json.loads(payload)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "bad_payload", "message": "Datos de análisis inválidos."})

    image_bytes = None
    if image is not None:
        image_bytes = await image.read()
        if image_bytes and len(image_bytes) > settings.max_image_bytes:
            image_bytes = None

    # Comprobar permiso Y consumir en una sola operación atómica: evita que
    # dos descargas simultáneas del mismo email se cuelen las dos.
    # Se consume ANTES de generar; si la generación falla, se devuelve el
    # crédito más abajo para no cobrarle un informe que nunca recibió.
    consumed = consume_if_allowed(email_norm)
    if not consumed:
        return JSONResponse(
            status_code=403,
            content={
                "error": "limit_reached",
                "message": "Has usado tu análisis gratuito. Contacta con nosotros para seguir.",
            },
        )

    lang = normalize_lang(lang)
    try:
        buffer = generar_informe(
            analisis,
            empresa=empresa.strip()[:120],
            centro=centro.strip()[:120],
            responsable=responsable.strip()[:120],
            resp_zona=resp_zona.strip()[:120],
            supervisor=supervisor.strip()[:120],
            lang=lang,
            image_bytes=image_bytes,
        )
    except Exception:
        # El informe no se ha llegado a generar: se devuelve lo consumido
        # para no cobrarle al usuario un informe que nunca recibió.
        logger.exception("Error generando el informe — devolviendo lo consumido")
        refund_consumption(email_norm, consumed)
        return JSONResponse(
            status_code=500,
            content={"error": "report_failed", "message": "No se pudo generar el informe. Inténtalo de nuevo."},
        )

    from i18n import report_strings
    filename = report_strings(lang)["filename"]
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Stripe: compra del bono Easy (5 informes, pago único) -----------------
@app.post("/api/checkout/easy")
async def checkout_easy(request: Request):
    """
    Crea una Stripe Checkout Session para el bono Easy y devuelve su URL.
    El frontend redirige el navegador a esa URL. No se crea ninguna cuenta
    ni se pide contraseña — Stripe pide el email dentro de su propio
    formulario de pago (modo invitado).
    """
    base_url = _public_base_url(request)
    try:
        checkout_url = stripe_service.create_easy_checkout_session(
            success_url=f"{base_url}/app?checkout=success",
            cancel_url=f"{base_url}/?checkout=cancelled",
        )
    except stripe_service.StripeConfigError as exc:
        logger.warning("Stripe no configurado: %s", exc)
        return JSONResponse(status_code=503, content={"error": "stripe_not_configured", "message": str(exc)})
    except Exception:
        logger.exception("Error creando la sesión de Stripe Checkout")
        return JSONResponse(
            status_code=502,
            content={"error": "stripe_error", "message": "No se pudo iniciar el pago. Inténtalo de nuevo."},
        )

    return JSONResponse(content={"checkout_url": checkout_url})


# --- Stripe: webhook (fuente de verdad de los pagos) ------------------------
@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Recibe los eventos de Stripe. Cuando se confirma el pago del bono Easy
    (checkout.session.completed), carga 5 créditos al email que la persona
    escribió en el Checkout de Stripe.

    IMPORTANTE: hay que dar de alta esta URL como endpoint de webhook en el
    dashboard de Stripe (Developers -> Webhooks) para que Stripe empiece a
    llamarla, y copiar el "Signing secret" que genera a la variable de
    entorno STRIPE_WEBHOOK_SECRET. Sin eso, Stripe nunca llega a avisarnos
    de los pagos y no se cargará ningún crédito, aunque el cobro sí se haya
    hecho correctamente en Stripe.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.verify_webhook(payload, sig_header)
    except stripe_service.StripeConfigError as exc:
        logger.warning("Webhook de Stripe recibido pero no configurado: %s", exc)
        return JSONResponse(status_code=503, content={"error": "stripe_not_configured"})
    except Exception:
        logger.warning("Webhook de Stripe con firma inválida — descartado.")
        return JSONResponse(status_code=400, content={"error": "invalid_signature"})

    if stripe_service.get_event_type(event) != "checkout.session.completed":
        # Otros eventos (p.ej. los que Stripe manda al crear el endpoint):
        # se aceptan con 200 para que Stripe no los reintente en bucle.
        return JSONResponse(content={"received": True, "ignored": stripe_service.get_event_type(event)})

    # --- Protección 1: idempotencia -----------------------------------------
    # Stripe REINTENTA los webhooks. Sin esto, el mismo pago cargaría el bono
    # varias veces y el cliente acabaría con 10 o 15 créditos habiendo pagado
    # una sola vez.
    event_id = stripe_service.get_event_id(event)
    if not mark_event_processed_if_new(event_id):
        logger.info("Evento de Stripe %s ya procesado — ignorado (reintento).", event_id or "sin-id")
        return JSONResponse(content={"received": True, "duplicate": True})

    # --- Protección 2: solo pagos realmente cobrados ------------------------
    # checkout.session.completed también llega con payment_status 'unpaid'
    # (pagos diferidos o pendientes). Cargar créditos ahí sería entregar
    # producto sin haber cobrado.
    if not stripe_service.is_paid_session(event):
        logger.warning("Sesión completada pero NO pagada (%s) — no se cargan créditos.", event_id)
        return JSONResponse(content={"received": True, "unpaid": True})

    if not stripe_service.is_easy_bundle(event):
        logger.info("Compra que no es el bono Easy (%s) — sin créditos que cargar.", event_id)
        return JSONResponse(content={"received": True, "not_easy_bundle": True})

    email = stripe_service.extract_paid_email(event)
    if not email:
        # No se puede vincular el bono a nadie. Se registra bien alto: hay un
        # cobro real sin producto entregado y hay que resolverlo a mano.
        logger.error("PAGO SIN EMAIL (%s) — cobro realizado sin poder cargar créditos. Revisar en Stripe.", event_id)
        return JSONResponse(content={"received": True, "no_email": True})

    email_norm = normalize_email(email)
    add_credits(email_norm, stripe_service.EASY_BUNDLE_CREDITS)
    stripe_service.on_checkout_completed_notify_invoicing(
        email_norm, stripe_service.get_amount_cents(event)
    )
    logger.info(
        "Bono Easy cargado: %s +%d créditos (evento %s)",
        email_norm, stripe_service.EASY_BUNDLE_CREDITS, event_id,
    )
    return JSONResponse(content={"received": True})
