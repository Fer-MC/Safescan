"""
config.py — Configuración central de H&S Detect.

Lee ANTHROPIC_API_KEY desde variables de entorno (seteadas por load_dotenv en main.py)
"""

import os


class Settings:
    """Configuración — lee valores dinámicamente desde el entorno."""
    
    def __init__(self):
        # Lee la clave EN ESTE MOMENTO (cuando se crea la instancia)
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        
        # Modelos
        self.MODEL_FREE = "claude-haiku-4-5-20251001"
        self.MODEL_PRO = "claude-sonnet-4-6"
        
        # Límites
        self.max_tokens = 4096
        self.max_image_bytes = 5 * 1024 * 1024
        self.allowed_mime = ("image/jpeg", "image/png", "image/webp", "image/gif")
        
        # Freemium
        self.free_analyses_limit = 3
        
        # App
        self.app_name = "H&S Detect"
        self.debug = os.getenv("DEBUG", "false").lower() == "true"


# Crear instancia única
settings = Settings()


def validate_runtime() -> list[str]:
    """Valida que la configuración sea correcta."""
    problems = []
    
    if not settings.anthropic_api_key:
        problems.append(
            "❌ ANTHROPIC_API_KEY vacía. Verifica que backend/.env existe con: "
            "ANTHROPIC_API_KEY=sk-ant-xxxxx"
        )
    elif not settings.anthropic_api_key.startswith("sk-ant-"):
        problems.append(
            f"⚠️  ANTHROPIC_API_KEY no válida (no empieza con 'sk-ant-'). "
            f"Valor actual: {settings.anthropic_api_key[:20]}..."
        )
    
    return problems
