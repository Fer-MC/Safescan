"""
report_service.py — Generación del informe de inspección en Word (python-docx).

Produce un INFORME DE INSPECCIÓN VISUAL DE APOYO, multiidioma (es/en/ca), con
una tabla por observación, branding y los disclaimers legales. El documento se
devuelve en memoria (BytesIO) para no escribir en disco en el servidor.

IMPORTANTE (legal): el documento se marca explícitamente como informe de APOYO
que NO sustituye la evaluación de riesgos legalmente exigible. Ver i18n.REPORT.
"""

from datetime import datetime
from io import BytesIO

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from i18n import CLASIF_LABEL, CONF_LABEL, normalize_lang, report_strings

# Paleta IMAFORT
AZUL    = RGBColor(0x1B, 0x2F, 0x4E)   # Navy #1B2F4E
NARANJA = RGBColor(0xE8, 0x61, 0x1A)   # Naranja seguridad #E8611A
GRIS    = RGBColor(0x4A, 0x55, 0x68)   # Gris acero #4A5568

# Color de fondo de celda por clasificación — paleta IMAFORT
COLOR_CLASIF = {
    "critical":  "F5B7B1",   # fondo suave rojo  → borde #A32D2D
    "important": "FAE5D3",   # fondo suave naranja → borde #E8611A
    "minor":     "FCF3CF",   # fondo suave amarillo
    "conform":   "D4EFDF",   # fondo suave verde  → borde #3B6D11
}


def _heading(doc, text, size=14, color=AZUL, space_before=10):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = color
    return p


def generar_informe(
    analisis: dict,
    *,
    empresa: str = "",
    centro: str = "",
    responsable: str = "",
    lang: str = "es",
) -> BytesIO:
    """Genera el .docx en memoria a partir del análisis normalizado."""
    lang = normalize_lang(lang)
    T = report_strings(lang)
    clabel = CLASIF_LABEL[lang]
    conflabel = CONF_LABEL[lang]

    doc = Document()

    # --- Cabecera ---
    titulo = doc.add_paragraph()
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = titulo.add_run("IMAFORT")
    r.bold = True
    r.font.size = Pt(26)
    r.font.color.rgb = AZUL

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rs = sub.add_run(T["app_subtitle"])
    rs.font.size = Pt(12)
    rs.font.color.rgb = NARANJA

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    parts = [f"{T['date']}: {datetime.now().strftime('%d/%m/%Y %H:%M')}"]
    if empresa:
        parts.append(f"{T['company']}: {empresa}")
    if centro:
        parts.append(f"{T['site']}: {centro}")
    if responsable:
        parts.append(f"{T['inspector']}: {responsable}")
    meta.add_run("  ·  ".join(parts)).font.size = Pt(9)

    # --- Aviso legal (discreto, al final del encabezado) ---
    _heading(doc, T["legal_heading"], size=11, color=GRIS)
    d = doc.add_paragraph()
    dr = d.add_run(T["legal"])
    dr.font.size = Pt(8)
    dr.italic = True

    # --- Resumen ---
    _heading(doc, T["summary_heading"])
    doc.add_paragraph(analisis.get("resumen") or T["no_summary"])
    n = analisis.get("num_observaciones", len(analisis.get("observaciones", [])))
    doc.add_paragraph(f"{T['obs_count']}: {n}").runs[0].bold = True

    # --- Observaciones ---
    _heading(doc, T["obs_heading"])
    observaciones = analisis.get("observaciones", [])
    if not observaciones:
        doc.add_paragraph(T["no_obs"])
    else:
        for i, obs in enumerate(observaciones, 1):
            _heading(doc, f"{i}. {obs.get('categoria', '')}", size=12, space_before=8)

            tabla = doc.add_table(rows=0, cols=2)
            tabla.style = "Light Grid Accent 1"

            def fila(k, v):
                cells = tabla.add_row().cells
                kp = cells[0].paragraphs[0]
                kr = kp.add_run(k)
                kr.bold = True
                kr.font.size = Pt(9)
                cells[1].paragraphs[0].add_run(str(v)).font.size = Pt(9)
                return cells

            fila(T["f_desc"], obs.get("descripcion", ""))
            if obs.get("ubicacion"):
                fila(T["f_loc"], obs.get("ubicacion", ""))
            clave = obs.get("clasificacion", "important")
            class_cells = fila(T["f_class"], clabel.get(clave, clave))
            _shade_cell(class_cells[1], COLOR_CLASIF.get(clave, "FFFFFF"))
            if obs.get("acciones"):
                fila(T["f_actions"], "\n".join(f"• {a}" for a in obs.get("acciones", [])))
            fila(T["f_norm"], ", ".join(obs.get("normativa", [])) or "—")
            fila(T["f_conf"], conflabel.get(obs.get("confianza", "medium")))

    # --- Limitaciones ---
    _heading(doc, T["limits_heading"])
    for lim in analisis.get("limitaciones", []) or [T["no_limits"]]:
        doc.add_paragraph(lim, style="List Bullet")

    # --- Validación / firma ---
    _heading(doc, T["valid_heading"])
    doc.add_paragraph(T["valid_text"])
    firma = doc.add_paragraph()
    firma.add_run("\n\n" + T["sign_line"])

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def _shade_cell(cell, hex_color: str):
    """Aplica color de fondo a una celda (python-docx no lo expone directamente)."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)
