"""
usage_store.py — Control de uso gratuito + créditos de pago (bono Easy) por email.

Guarda en un fichero JSON, por email:
  - si ya ha gastado su informe gratuito de prueba (free_used)
  - los lotes de créditos comprados, cada uno con su fecha de caducidad
    (el bono Easy es válido 12 meses desde la compra)

Además guarda qué eventos de Stripe ya se han procesado, para que un
reintento de webhook no cargue el bono dos veces.

No es la base de datos de Comfort/Enterprise — es una solución ligera
para validación y para el tier Easy mientras no exista Postgres.

⚠️ ESTO GUARDA DATOS LIGADOS A DINERO REAL. Es aceptable para modo TEST
de Stripe y el volumen de esta fase. Antes de activar Stripe en modo REAL
debería migrar a base de datos (la misma que se monte para Comfort).

⚠️ PERSISTENCIA EN RAILWAY: el disco del contenedor es EFÍMERO. Cada deploy
borra este fichero salvo que esté en un Volume montado y USAGE_STORE_PATH
apunte ahí:  USAGE_STORE_PATH=/data/usage_store.json

⚠️ UN SOLO WORKER. El lock es de proceso, no entre procesos. No arranques
uvicorn con --workers > 1 sin migrar antes a base de datos.
"""

import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

STORE_PATH = Path(os.getenv("USAGE_STORE_PATH", str(Path(__file__).parent / "usage_store.json")))

# Emails sin límite (uso interno / testing). Añadir aquí los que hagan falta.
UNLIMITED_EMAILS = [
    "fermc1983@gmail.com",
]

# Validez del bono Easy: 12 meses desde la compra (prometido en la landing
# y en la descripción del producto que ve el cliente en Stripe).
BUNDLE_VALIDITY_DAYS = 365

# Cuánto guardamos los IDs de evento de Stripe ya procesados. Stripe reintenta
# durante ~3 días; 30 da margen de sobra sin que el fichero crezca sin control.
PROCESSED_EVENT_RETENTION_DAYS = 30

_lock = threading.Lock()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Utilidades de email ----------------------------------------------------
def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    """Validación básica de formato, no exhaustiva (suficiente para filtrar erratas)."""
    return bool(_EMAIL_RE.match(normalize_email(email)))


def is_whitelisted(email: str) -> bool:
    return normalize_email(email) in {e.lower() for e in UNLIMITED_EMAILS}


# --- Persistencia -----------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(iso_str: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _read_store() -> dict:
    """
    Lee el fichero y lo devuelve SIEMPRE en el formato actual (v2):
        {"_meta": {...}, "users": {...}, "processed_events": {...}}
    Migra de forma transparente el formato antiguo (v1: mapa plano
    email -> {"used_at": ...}) sin perder los datos ya guardados.
    """
    if not STORE_PATH.exists():
        return {"_meta": {"version": 2}, "users": {}, "processed_events": {}}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Fichero corrupto o ilegible: se trata como vacío en vez de tumbar
        # el endpoint de descarga.
        return {"_meta": {"version": 2}, "users": {}, "processed_events": {}}

    if isinstance(raw, dict) and "_meta" in raw:
        raw.setdefault("users", {})
        raw.setdefault("processed_events", {})
        return raw

    # Formato antiguo: cada clave era un email que ya había gastado su gratuito.
    users = {}
    if isinstance(raw, dict):
        for email, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            users[email] = {
                "free_used": entry.get("free_used", True),
                "credit_batches": [],
                "last_used_at": entry.get("used_at") or entry.get("last_used_at"),
            }
    return {"_meta": {"version": 2}, "users": users, "processed_events": {}}


def _write_store(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STORE_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(STORE_PATH)  # escritura atómica


def _user(data: dict, email: str) -> dict:
    return data["users"].get(email) or {"free_used": False, "credit_batches": [], "last_used_at": None}


def _live_batches(user: dict, now: datetime) -> list[dict]:
    """Lotes de créditos que aún tienen saldo y no han caducado."""
    live = []
    for batch in user.get("credit_batches", []):
        if batch.get("credits", 0) <= 0:
            continue
        expires = _parse(batch.get("expires_at", ""))
        if expires is not None and expires <= now:
            continue  # caducado
        live.append(batch)
    # Consumir primero el lote que caduca antes.
    live.sort(key=lambda b: _parse(b.get("expires_at", "")) or now)
    return live


# --- API pública ------------------------------------------------------------
def has_used_free_report(email: str) -> bool:
    """True si ese email ya ha gastado su informe gratuito de prueba."""
    email = normalize_email(email)
    with _lock:
        data = _read_store()
    return bool(_user(data, email).get("free_used"))


def get_credits(email: str) -> int:
    """Créditos de pago NO caducados que le quedan a ese email."""
    email = normalize_email(email)
    now = _now()
    with _lock:
        data = _read_store()
    return sum(b.get("credits", 0) for b in _live_batches(_user(data, email), now))


def add_credits(email: str, n: int, *, validity_days: int = BUNDLE_VALIDITY_DAYS) -> None:
    """
    Añade un lote de créditos con su fecha de caducidad. Se llama desde el
    webhook de Stripe al confirmar una compra del bono Easy.
    """
    email = normalize_email(email)
    now = _now()
    with _lock:
        data = _read_store()
        user = _user(data, email)
        user.setdefault("credit_batches", []).append({
            "credits": n,
            "purchased_at": _iso(now),
            "expires_at": _iso(now + timedelta(days=validity_days)),
        })
        data["users"][email] = user
        _write_store(data)


def can_download(email: str) -> bool:
    """
    Consulta de solo lectura: ¿este email podría descargar ahora mismo?
    Para el flujo real de descarga usa consume_if_allowed(), que es atómico.
    """
    if is_whitelisted(email):
        return True
    email = normalize_email(email)
    now = _now()
    with _lock:
        data = _read_store()
    user = _user(data, email)
    if _live_batches(user, now):
        return True
    return not user.get("free_used")


def consume_if_allowed(email: str) -> str | None:
    """
    Comprueba el permiso Y consume el informe en una sola operación atómica,
    para que dos descargas simultáneas del mismo email no puedan colarse
    ambas.

    Devuelve qué se ha consumido —"whitelist", "credit" o "free"— o None si
    se deniega. El valor de retorno es truthy/falsy, así que sirve
    directamente como condición, y a la vez permite devolver exactamente lo
    mismo que se consumió si luego falla la generación (ver refund_consumption).

    Prioridad: primero gasta créditos de pago (el lote que antes caduca),
    y solo si no hay ninguno, gasta el informe gratuito de prueba.
    """
    if is_whitelisted(email):
        return "whitelist"  # la whitelist nunca consume nada

    email = normalize_email(email)
    now = _now()
    consumed: str
    with _lock:
        data = _read_store()
        user = _user(data, email)

        live = _live_batches(user, now)
        if live:
            live[0]["credits"] -= 1
            consumed = "credit"
        elif not user.get("free_used"):
            user["free_used"] = True
            consumed = "free"
        else:
            return None  # sin créditos y sin gratuito disponible

        # Limpieza: descartar solo los lotes CADUCADOS. Los lotes agotados
        # (0 créditos) se conservan hasta su caducidad para poder devolver
        # el crédito al lote correcto si la generación del informe falla.
        user["credit_batches"] = [
            b for b in user.get("credit_batches", [])
            if (_parse(b.get("expires_at", "")) or now) > now
        ]
        user["last_used_at"] = _iso(now)
        data["users"][email] = user
        _write_store(data)
        return consumed


# --- Idempotencia de webhooks de Stripe -------------------------------------
def mark_event_processed_if_new(event_id: str) -> bool:
    """
    Registra un evento de Stripe como procesado. Devuelve True si es la
    primera vez que se ve (hay que procesarlo) y False si ya estaba
    registrado (es un reintento y hay que ignorarlo).

    Sin esto, un reintento de webhook cargaría el bono dos veces.
    """
    if not event_id:
        # Sin ID no podemos deduplicar; es más seguro no procesar.
        return False
    now = _now()
    with _lock:
        data = _read_store()
        processed = data.setdefault("processed_events", {})
        if event_id in processed:
            return False

        # Purga de IDs antiguos para que el fichero no crezca sin control.
        cutoff = now - timedelta(days=PROCESSED_EVENT_RETENTION_DAYS)
        for old_id in [k for k, v in processed.items() if (_parse(v) or now) < cutoff]:
            processed.pop(old_id, None)

        processed[event_id] = _iso(now)
        _write_store(data)
        return True


def refund_consumption(email: str, consumed: str | None) -> None:
    """
    Devuelve exactamente lo que consumió consume_if_allowed(), para usar
    cuando la generación del informe falla después de haber consumido.
    Sin esto, un error del servidor le costaría al usuario un informe que
    nunca llegó a recibir.
    """
    if not consumed or consumed == "whitelist":
        return
    email = normalize_email(email)
    now = _now()
    with _lock:
        data = _read_store()
        user = _user(data, email)

        if consumed == "free":
            user["free_used"] = False
        else:  # "credit"
            # Reingresar en un lote no caducado (aunque esté a 0), el que
            # antes caduque. Si no queda ninguno, se crea uno nuevo.
            candidatos = [
                b for b in user.get("credit_batches", [])
                if (_parse(b.get("expires_at", "")) or now) > now
            ]
            candidatos.sort(key=lambda b: _parse(b.get("expires_at", "")) or now)
            if candidatos:
                candidatos[0]["credits"] = candidatos[0].get("credits", 0) + 1
            else:
                user.setdefault("credit_batches", []).append({
                    "credits": 1,
                    "purchased_at": _iso(now),
                    "expires_at": _iso(now + timedelta(days=BUNDLE_VALIDITY_DAYS)),
                })

        data["users"][email] = user
        _write_store(data)
