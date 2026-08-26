"""
usage_store.py — Control simple de uso gratuito por email.

Guarda en un fichero JSON qué emails ya han descargado su informe gratuito,
para aplicar el tope de "1 informe gratis por email" descrito en el brief
de producto/GTM. No es la base de datos de Comfort/Enterprise — es una
solución ligera pensada solo para la fase de validación.

⚠️ PERSISTENCIA EN RAILWAY — LEER ANTES DE CONFIAR EN ESTO EN PRODUCCIÓN:
El sistema de archivos de un contenedor de Railway es EFÍMERO. Cada vez
que se hace un nuevo deploy (cualquier `git push` a main dispara uno), el
contenedor se reconstruye desde cero y este fichero desaparece — el tope
de TODOS los emails se resetea silenciosamente. Para que sobreviva a los
despliegues hace falta montar un Volume en Railway y apuntar la variable
de entorno USAGE_STORE_PATH a una ruta dentro de ese volumen, por ejemplo:

    USAGE_STORE_PATH=/data/usage_store.json

Sin ese volumen, la función sigue funcionando día a día, pero dejará
pasar usuarios que ya habían agotado su tope en cuanto subáis código nuevo.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

# Ruta del almacén. Configurable por entorno para poder apuntar a un Volume
# de Railway sin tocar código (ver aviso de persistencia arriba).
STORE_PATH = Path(os.getenv("USAGE_STORE_PATH", str(Path(__file__).parent / "usage_store.json")))

# Emails sin límite (uso interno / testing). Añadir aquí los que hagan falta.
UNLIMITED_EMAILS = [
    "fermc1983@gmail.com",
]

_lock = threading.Lock()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    """Validación básica de formato, no exhaustiva (suficiente para filtrar erratas)."""
    return bool(_EMAIL_RE.match(normalize_email(email)))


def is_whitelisted(email: str) -> bool:
    return normalize_email(email) in {e.lower() for e in UNLIMITED_EMAILS}


def _read_store() -> dict:
    if not STORE_PATH.exists():
        return {}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Fichero corrupto o ilegible: se trata como si estuviera vacío en
        # vez de tumbar el endpoint de descarga.
        return {}


def _write_store(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STORE_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(STORE_PATH)  # escritura atómica


def has_used_free_report(email: str) -> bool:
    """True si ese email ya ha descargado su informe gratuito alguna vez."""
    email = normalize_email(email)
    with _lock:
        data = _read_store()
    return email in data


def record_usage(email: str) -> None:
    """Registra que ese email acaba de usar su informe gratuito."""
    email = normalize_email(email)
    with _lock:
        data = _read_store()
        data[email] = {"used_at": datetime.now(timezone.utc).isoformat()}
        _write_store(data)


def can_download(email: str) -> bool:
    """
    Regla central del tope: los emails de la whitelist siempre pueden
    descargar; el resto, solo la primera vez.
    """
    if is_whitelisted(email):
        return True
    return not has_used_free_report(email)
