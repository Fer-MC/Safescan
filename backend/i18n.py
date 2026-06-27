"""
i18n.py — Centro único de textos, prompts y metadatos multiidioma.

Idiomas soportados: es (español), en (English), ca (català).

Principio de diseño:
  - La lógica interna usa CLAVES NEUTRAS para clasificación y confianza
    (critical/important/minor/conform · high/medium/low).
  - La traducción a etiquetas visibles ocurre SOLO al renderizar (web o Word).
  - Esto evita inconsistencias cuando el modelo responde en distintos idiomas.

Enfoque del producto:
  - NO es una evaluación de riesgos (Probabilidad x Consecuencias).
  - ES una INSPECCIÓN / OBSERVACIÓN de seguridad: se registran hallazgos
    visibles y se clasifican por severidad de la observación.
"""

SUPPORTED_LANGS = ("es", "en", "ca")
DEFAULT_LANG = "es"

# Claves neutras de clasificación de la observación (no traducir: son IDs internos)
CLASIF_KEYS = ("critical", "important", "minor", "conform")
CLASIF_ORDER = {"critical": 0, "important": 1, "minor": 2, "conform": 3}

# Claves neutras de confianza
CONF_KEYS = ("high", "medium", "low")


def normalize_lang(lang: str | None) -> str:
    """Devuelve un idioma soportado; cae a DEFAULT_LANG si no se reconoce."""
    if not lang:
        return DEFAULT_LANG
    code = lang.strip().lower()[:2]
    return code if code in SUPPORTED_LANGS else DEFAULT_LANG


# --- Etiquetas visibles por idioma ----------------------------------------
CLASIF_LABEL = {
    "es": {"critical": "Crítica", "important": "Importante", "minor": "Menor", "conform": "Conforme"},
    "en": {"critical": "Critical", "important": "Important", "minor": "Minor", "conform": "Compliant"},
    "ca": {"critical": "Crítica", "important": "Important", "minor": "Menor", "conform": "Conforme"},
}

CONF_LABEL = {
    "es": {"high": "Alta", "medium": "Media", "low": "Baja"},
    "en": {"high": "High", "medium": "Medium", "low": "Low"},
    "ca": {"high": "Alta", "medium": "Mitjana", "low": "Baixa"},
}

# Nombre del idioma para instruir al modelo sobre el idioma de redacción
LANG_NAME = {"es": "español", "en": "English", "ca": "català"}


# --- Textos del informe Word -----------------------------------------------
REPORT = {
    "es": {
        "app_subtitle": "Informe de inspección y observación de seguridad",
        "date": "Fecha",
        "company": "Empresa",
        "site": "Centro de trabajo",
        "inspector": "Responsable de la inspección",
        "legal_heading": "Aviso legal importante",
        "summary_heading": "Resumen de la inspección",
        "no_summary": "Sin resumen disponible.",
        "obs_count": "Observaciones registradas",
        "obs_heading": "Observaciones de seguridad",
        "no_obs": "No se registraron observaciones visibles en las imágenes.",
        "f_desc": "Descripción de la observación",
        "f_loc": "Ubicación",
        "f_class": "Clasificación",
        "f_actions": "Acción recomendada",
        "f_norm": "Normativa de referencia",
        "f_conf": "Confianza del análisis",
        "f_verify": "¿Requiere verificación presencial?",
        "yes": "Sí", "no": "No",
        "limits_heading": "Limitaciones del análisis automático",
        "no_limits": "No se especificaron limitaciones.",
        "valid_heading": "Validación",
        "valid_text": ("Esta inspección visual es una herramienta de apoyo. Las observaciones "
                       "deben ser revisadas y validadas presencialmente por personal competente "
                       "en prevención de riesgos laborales:"),
        "sign_line": "Responsable: ____________________   Función: __________   Fecha: __________",
        "legal": ("AVISO LEGAL — Este documento es un INFORME DE INSPECCIÓN VISUAL DE APOYO "
                  "generado mediante análisis automático de imágenes con inteligencia artificial. "
                  "Registra observaciones de seguridad visibles y NO constituye ni sustituye la "
                  "evaluación de riesgos laborales exigida por la Ley 31/1995 y el RD 39/1997, "
                  "que debe realizar personal cualificado. El análisis se limita a lo visible en "
                  "las imágenes aportadas y puede contener errores u omisiones. La empresa usuaria "
                  "es responsable de validar y completar las observaciones conforme a la normativa vigente."),
        "filename": "Informe_inspeccion_HS_Detect.docx",
    },
    "en": {
        "app_subtitle": "Safety inspection & observation report",
        "date": "Date",
        "company": "Company",
        "site": "Work site",
        "inspector": "Inspection lead",
        "legal_heading": "Important legal notice",
        "summary_heading": "Inspection summary",
        "no_summary": "No summary available.",
        "obs_count": "Observations recorded",
        "obs_heading": "Safety observations",
        "no_obs": "No visible observations were recorded in the images.",
        "f_desc": "Observation description",
        "f_loc": "Location",
        "f_class": "Classification",
        "f_actions": "Recommended action",
        "f_norm": "Reference regulation",
        "f_conf": "Analysis confidence",
        "f_verify": "On-site verification required?",
        "yes": "Yes", "no": "No",
        "limits_heading": "Limitations of the automated analysis",
        "no_limits": "No limitations were specified.",
        "valid_heading": "Validation",
        "valid_text": ("This visual inspection is a support tool. Observations must be reviewed "
                       "and validated on-site by personnel competent in occupational health and safety:"),
        "sign_line": "Responsible: ____________________   Role: __________   Date: __________",
        "legal": ("LEGAL NOTICE — This document is a SUPPORTING VISUAL INSPECTION REPORT generated "
                  "through automated image analysis with artificial intelligence. It records visible "
                  "safety observations and does NOT constitute or replace the occupational risk "
                  "assessment required by Spanish Law 31/1995 and RD 39/1997, which must be carried "
                  "out by qualified personnel. The analysis is limited to what is visible in the "
                  "supplied images and may contain errors or omissions. The user company is responsible "
                  "for validating and completing the observations in accordance with applicable regulations."),
        "filename": "HS_Detect_inspection_report.docx",
    },
    "ca": {
        "app_subtitle": "Informe d'inspecció i observació de seguretat",
        "date": "Data",
        "company": "Empresa",
        "site": "Centre de treball",
        "inspector": "Responsable de la inspecció",
        "legal_heading": "Avís legal important",
        "summary_heading": "Resum de la inspecció",
        "no_summary": "Sense resum disponible.",
        "obs_count": "Observacions registrades",
        "obs_heading": "Observacions de seguretat",
        "no_obs": "No s'han registrat observacions visibles a les imatges.",
        "f_desc": "Descripció de l'observació",
        "f_loc": "Ubicació",
        "f_class": "Classificació",
        "f_actions": "Acció recomanada",
        "f_norm": "Normativa de referència",
        "f_conf": "Confiança de l'anàlisi",
        "f_verify": "Requereix verificació presencial?",
        "yes": "Sí", "no": "No",
        "limits_heading": "Limitacions de l'anàlisi automàtica",
        "no_limits": "No s'han especificat limitacions.",
        "valid_heading": "Validació",
        "valid_text": ("Aquesta inspecció visual és una eina de suport. Les observacions s'han de "
                       "revisar i validar presencialment per personal competent en prevenció de "
                       "riscos laborals:"),
        "sign_line": "Responsable: ____________________   Funció: __________   Data: __________",
        "legal": ("AVÍS LEGAL — Aquest document és un INFORME D'INSPECCIÓ VISUAL DE SUPORT generat "
                  "mitjançant anàlisi automàtica d'imatges amb intel·ligència artificial. Registra "
                  "observacions de seguretat visibles i NO constitueix ni substitueix l'avaluació de "
                  "riscos laborals exigida per la Llei 31/1995 i el RD 39/1997, que ha de fer personal "
                  "qualificat. L'anàlisi es limita al que és visible a les imatges aportades i pot "
                  "contenir errors o omissions. L'empresa usuària és responsable de validar i completar "
                  "les observacions d'acord amb la normativa vigent."),
        "filename": "Informe_inspeccio_HS_Detect.docx",
    },
}


def report_strings(lang: str) -> dict:
    return REPORT[normalize_lang(lang)]


# --- Prompts para Claude ----------------------------------------------------
# Instrucciones en español (el modelo es bilingüe), pero se le ordena redactar
# TODOS los textos libres en el idioma de salida. Las claves del JSON son neutras.

def build_system_prompt(lang: str) -> str:
    lang = normalize_lang(lang)
    idioma = LANG_NAME[lang]
    return f"""Eres un asistente técnico de apoyo en INSPECCIONES Y OBSERVACIONES DE \
SEGURIDAD en entornos de trabajo industriales en España. Tu función es ayudar a un \
responsable a registrar OBSERVACIONES de seguridad visibles en fotografías durante una \
visita o inspección. NO realizas una evaluación de riesgos laborales legal.

Reglas estrictas:
1. Registra SOLO observaciones razonablemente visibles en la imagen. No inventes \
hallazgos que no puedas ver.
2. Clasifica cada observación con UNA de estas claves EXACTAS (en inglés, no traducir):
   - "critical": peligro inminente, requiere acción inmediata.
   - "important": deficiencia clara, corregir en plazo corto.
   - "minor": mejora recomendable o desviación leve.
   - "conform": situación correcta / buena práctica observada (refuerzo positivo).
3. Para cada observación indica tu confianza con UNA clave EXACTA: "high", "medium" o "low", \
y si requiere verificación presencial.
4. Cita normativa española aplicable SOLO si la conoces con seguridad (p.ej. RD 1215/1997 \
equipos de trabajo, RD 486/1997 lugares de trabajo, RD 773/1997 EPI, RD 614/2001 riesgo \
Eléctrico). Mantén el código de la norma tal cual; si no estás seguro, deja la lista vacía.
5. Enumera las LIMITACIONES: qué NO puede observarse desde una foto (ruido, exposición \
química, ergonomía por repetición, factores organizativos, instalaciones ocultas, etc.).

IDIOMA DE RESPUESTA — OBLIGATORIO: Todos los textos libres del JSON (resumen, categoria, descripcion, ubicacion, acciones, limitaciones) deben estar redactados EXCLUSIVAMENTE en {idioma}. Está PROHIBIDO mezclar otros idiomas. Si el idioma es català, escribe en català, no en castellano. Las claves del JSON y los valores de "clasificacion" y "confianza" permanecen siempre en inglés.

Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional ni markdown, con esta \
estructura exacta:
{{
  "resumen": "string, 1-2 frases",
  "observaciones": [
    {{
      "categoria": "string (p.ej. Orden y limpieza, EPI, Riesgo eléctrico)",
      "descripcion": "string",
      "ubicacion": "string (dónde en la imagen)",
      "clasificacion": "critical|important|minor|conform",
      "acciones": ["string", "..."],
      "normativa": ["string", "..."],
      "confianza": "high|medium|low",
      "requiere_verificacion": true
    }}
  ],
  "limitaciones": ["string", "..."]
}}"""


USER_PROMPT = {
    "es": "Inspecciona esta imagen de un entorno de trabajo y registra las observaciones de seguridad visibles según las instrucciones. Devuelve solo el JSON.",
    "en": "Inspect this image of a workplace and record the visible safety observations following the instructions. Return only the JSON.",
    "ca": "Inspecciona aquesta imatge d'un entorn de treball i registra les observacions de seguretat visibles segons les instruccions. Retorna només el JSON.",
}


def user_prompt(lang: str) -> str:
    return USER_PROMPT[normalize_lang(lang)]
