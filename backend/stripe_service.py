"""
stripe_service.py — Integración con Stripe para el tier Easy (bono de 5
informes, pago único, modo invitado — sin cuenta ni contraseña).

Flujo:
  1. El usuario pulsa "Comprar bono" en la landing.
  2. El backend crea una Stripe Checkout Session (hosted, guest) y devuelve
     la URL de Stripe; el navegador redirige ahí.
  3. Stripe cobra y redirige de vuelta a success_url / cancel_url.
  4. En paralelo (no depende del navegador), Stripe llama a nuestro webhook
     con checkout.session.completed — ahí se cargan los créditos, NO en el
     redirect: el redirect puede interrumpirse (cerrar pestaña, perder red)
     y el webhook es la única fuente de verdad de que se ha cobrado.

Comfort (suscripción) NO se integra todavía — requiere cuentas de usuario
y base de datos. Este módulo es exclusivamente para Easy.

CONFIGURACIÓN NECESARIA (variables de entorno):
  STRIPE_SECRET_KEY       — clave secreta (modo test: sk_test_...)
  STRIPE_WEBHOOK_SECRET   — secreto de firma del webhook (whsec_...), se
                            obtiene al dar de alta el endpoint en Stripe.
  PUBLIC_BASE_URL         — URL pública del sitio, p.ej.
                            https://web-production-8ad37.up.railway.app
                            Necesaria porque detrás del proxy de Railway la
                            app no puede deducir con fiabilidad su propia
                            URL https (ver nota en main.py).

Sin las claves, el módulo lanza un error claro en vez de fallar en silencio.
"""

import logging
import os

import stripe

logger = logging.getLogger("vetlla.stripe")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

# Bono Easy: 5 informes por 15€, pago único, válido 12 meses.
# La validez se aplica en usage_store.BUNDLE_VALIDITY_DAYS.
EASY_BUNDLE_CREDITS = 5
EASY_BUNDLE_PRICE_EUR_CENTS = 1500

stripe.api_key = STRIPE_SECRET_KEY


class StripeConfigError(Exception):
    """Falta configuración de Stripe (claves no puestas todavía)."""


def is_configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


def create_easy_checkout_session(*, success_url: str, cancel_url: str) -> str:
    """
    Crea una Checkout Session para el bono Easy y devuelve la URL a la que
    redirigir. Modo invitado: Stripe pide el email en su propio formulario,
    no hace falta cuenta ni tenerlo de antes.
    """
    if not is_configured():
        raise StripeConfigError(
            "Falta configurar STRIPE_SECRET_KEY. La compra del bono Easy no está disponible todavía."
        )

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "unit_amount": EASY_BUNDLE_PRICE_EUR_CENTS,
                    "product_data": {
                        "name": "VETLLA — Bono Easy (5 informes)",
                        "description": "5 informes de inspección de seguridad. Válido 12 meses desde la compra.",
                    },
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        # Marca de qué producto es, para poder distinguirlo en el webhook
        # cuando en el futuro haya más de un tipo de compra (p.ej. Comfort).
        metadata={"product": "easy_bundle", "credits": str(EASY_BUNDLE_CREDITS)},
    )
    return session.url


def verify_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Verifica la firma del webhook y devuelve el evento como DICCIONARIO PLANO.
    Sin la verificación, cualquiera que conociera la URL podría enviarnos
    eventos falsos y auto-cargarse créditos gratis.

    Se devuelve dict y no el objeto Event del SDK a propósito: el objeto
    StripeObject no soporta .get() y hace saltar un AttributeError en cuanto
    se accede a él como un diccionario normal. Convertirlo aquí, en un único
    sitio, evita ese fallo en todo el código que consume el evento.

    Lanza SignatureVerificationError si la firma no es válida.
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise StripeConfigError(
            "Falta configurar STRIPE_WEBHOOK_SECRET. No se puede verificar el webhook de Stripe."
        )
    event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    if hasattr(event, "to_dict_recursive"):
        return event.to_dict_recursive()
    if hasattr(event, "to_dict"):
        return dict(event.to_dict())
    return dict(event)


def _as_dict(obj) -> dict:
    """Acepta dict o StripeObject y devuelve siempre un dict manejable."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for meth in ("to_dict_recursive", "to_dict"):
        if hasattr(obj, meth):
            try:
                return dict(getattr(obj, meth)())
            except Exception:
                pass
    try:
        return dict(obj)
    except Exception:
        return {}


def get_event_id(event) -> str:
    """ID único del evento de Stripe, usado para no procesar dos veces un reintento."""
    return _as_dict(event).get("id", "") or ""


def get_event_type(event) -> str:
    return _as_dict(event).get("type", "") or ""


def _session_of(event) -> dict:
    data = _as_dict(_as_dict(event).get("data"))
    return _as_dict(data.get("object"))


def is_paid_session(event) -> bool:
    """
    True solo si el pago está realmente cobrado.

    checkout.session.completed también se dispara con payment_status
    'unpaid' o 'no_payment_required' (métodos de pago diferidos, pagos
    pendientes de confirmación). Cargar créditos en esos casos sería
    entregar producto sin haber cobrado.
    """
    return _session_of(event).get("payment_status") == "paid"


def is_easy_bundle(event) -> bool:
    """
    True si esta compra corresponde al bono Easy. Hoy es el único producto
    con self-checkout, pero dejarlo explícito evita que en el futuro un
    evento de Comfort acabe cargando créditos de Easy por error.
    """
    session = _session_of(event)
    metadata = _as_dict(session.get("metadata"))
    # Si no hay metadata (sesiones creadas antes de añadirla), se asume Easy
    # porque es el único producto con checkout automático en esta fase.
    return metadata.get("product", "easy_bundle") == "easy_bundle"


def extract_paid_email(event) -> str | None:
    """
    Extrae el email que la persona escribió en el Checkout de Stripe.
    Devuelve None si el evento no trae ninguno.
    """
    session = _session_of(event)
    details = _as_dict(session.get("customer_details"))
    return details.get("email") or session.get("customer_email")


def get_amount_cents(event) -> int:
    return _session_of(event).get("amount_total") or 0


def on_checkout_completed_notify_invoicing(email: str, amount_cents: int) -> None:
    """
    Punto de enganche preparado para el punto 6 del brief ("dejar el webhook
    listo para conectar facturación sin rehacer la integración"). Hoy solo
    registra en el log — cuando exista herramienta de facturación conectada
    (Verifactu, obligatorio para autónomos desde julio 2027), esta función
    es el único sitio a tocar.
    """
    logger.info(
        "Pago Easy confirmado (%s, %d cts) — facturación aún no conectada.",
        email, amount_cents,
    )
