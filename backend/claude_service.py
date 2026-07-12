"""
claude_service.py — Integración con Claude Vision para INSPECCIONES de seguridad.

Responsabilidad única: recibir una imagen, pedir a Claude que registre
OBSERVACIONES de seguridad visibles (no una evaluación de riesgos) y devolver
JSON validado y normalizado, en el idioma solicitado.

Decisiones de diseño:
  - Enfoque "observación de seguridad": cada hallazgo se clasifica directamente
    como critical/important/minor/conform (claves neutras), no mediante la
    matriz Probabilidad x Consecuencias del INSST.
  - Las claves de clasificación y confianza son neutras (en inglés) para que la
    lógica no dependa del idioma; la traducción ocurre al renderizar.
  - Cada observación lleva 'confianza' y 'requiere_verificacion' para no
    sobrevender la fiabilidad del análisis automático.
  - Manejo de errores explícito (clave ausente, 429, 529, JSON inválido).
"""

import base64
import json
import logging

import anthropic

from config import settings
from i18n import (
    CLASIF_KEYS,
    CLASIF_ORDER,
    CONF_KEYS,
    build_system_prompt,
    normalize_lang,
    user_prompt,
)

logger = logging.getLogger("vetlla.claude")


class AnalysisError(Exception):
    """Error de negocio legible para el usuario final."""

    def __init__(self, message: str, *, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


def _build_image_block(image_bytes: bytes, mime_type: str) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
        },
    }


def _parse_model_json(text: str) -> dict:
    """Extrae y parsea el JSON de la respuesta del modelo de forma defensiva."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise AnalysisError(
            "El análisis no devolvió un resultado interpretable. "
            "Inténtalo de nuevo con otra foto.",
            status=502,
        )
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("JSON inválido del modelo: %s", exc)
        raise AnalysisError(
            "No se pudo interpretar el resultado del análisis. Inténtalo de nuevo.",
            status=502,
        )


def _normalize(raw: dict) -> dict:
    """Valida y normaliza la salida del modelo (claves neutras)."""
    obs_out = []
    # Acepta tanto "observaciones" (nuevo) como "riesgos" (compat. antigua).
    items = raw.get("observaciones") or raw.get("riesgos") or []
    for o in items:
        clasif = o.get("clasificacion")
        if clasif not in CLASIF_KEYS:
            clasif = "important"  # valor prudente por defecto
        conf = o.get("confianza")
        if conf not in CONF_KEYS:
            conf = "medium"
        obs_out.append(
            {
                "categoria": str(o.get("categoria", "Sin categorizar"))[:120],
                "descripcion": str(o.get("descripcion", ""))[:600],
                "ubicacion": str(o.get("ubicacion", ""))[:200],
                "clasificacion": clasif,
                "acciones": [str(a)[:300] for a in (o.get("acciones") or o.get("medidas") or [])][:8],
                "normativa": [str(n)[:120] for n in (o.get("normativa") or [])][:6],
                "confianza": conf,
                "requiere_verificacion": bool(o.get("requiere_verificacion", True)),
            }
        )

    # Orden por severidad: crítico primero, conforme al final.
    obs_out.sort(key=lambda x: CLASIF_ORDER.get(x["clasificacion"], 99))

    return {
        "resumen": str(raw.get("resumen", ""))[:500],
        "observaciones": obs_out,
        "num_observaciones": len(obs_out),
        "limitaciones": [str(l)[:300] for l in (raw.get("limitaciones") or [])][:10],
    }


def analizar_imagen(
    image_bytes: bytes,
    mime_type: str,
    *,
    lang: str = "es",
    model: str | None = None,
) -> dict:
    """
    Envía una imagen a Claude Vision y devuelve observaciones normalizadas.

    Lanza AnalysisError (con .status y .message legibles) ante cualquier fallo.
    """
    if not settings.anthropic_api_key:
        raise AnalysisError(
            "El servicio no está configurado correctamente (falta la clave de IA).",
            status=500,
        )

    lang = normalize_lang(lang)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = model or settings.MODEL_PRO

    try:
        response = client.messages.create(
            model=model,
            max_tokens=settings.max_tokens,
            system=build_system_prompt(lang),
            messages=[
                {
                    "role": "user",
                    "content": [
                        _build_image_block(image_bytes, mime_type),
                        {"type": "text", "text": user_prompt(lang)},
                    ],
                }
            ],
        )
    except anthropic.AuthenticationError:
        raise AnalysisError("Error de autenticación con el servicio de IA.", status=500)
    except anthropic.RateLimitError:
        raise AnalysisError(
            "Hay mucha demanda en este momento. Espera unos segundos e inténtalo de nuevo.",
            status=429,
        )
    except anthropic.APIStatusError as exc:
        logger.error("Error de la API de Claude: %s", exc)
        raise AnalysisError(
            "El servicio de análisis no está disponible ahora mismo. Inténtalo más tarde.",
            status=503,
        )
    except anthropic.APIConnectionError:
        raise AnalysisError("No se pudo conectar con el servicio de análisis.", status=503)

    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise AnalysisError("El análisis devolvió una respuesta vacía.", status=502)

    return _normalize(_parse_model_json(text))
