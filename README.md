# H&S Detect — MVP

Análisis de riesgos laborales (PRL) a partir de fotografías, usando Claude Vision.
**Herramienta de apoyo: no sustituye la evaluación de riesgos legal.**

## Qué hace este MVP
1. Subes una foto de un puesto/área de trabajo.
2. El backend la envía a Claude Vision con un prompt orientado a PRL.
3. Claude pre-identifica riesgos visibles; el backend calcula el **nivel de
   riesgo** con la matriz del INSST (Probabilidad × Consecuencias).
4. Se muestran los resultados ordenados por gravedad.
5. Se genera un **borrador de informe en Word** con disclaimers legales.

## Arquitectura
```
hs-detect/
├── backend/
│   ├── main.py            # FastAPI: endpoints, validación, contador freemium
│   ├── claude_service.py  # Integración Claude Vision + matriz INSST
│   ├── report_service.py  # Generación del Word (python-docx)
│   └── config.py          # Configuración (lee .env)
├── frontend/
│   └── index.html         # UI completa (HTML+CSS+JS), mobile-first
├── requirements.txt
└── .env.example
```
La clave de IA vive **solo en el backend**. El frontend nunca la ve.

## Instalación y arranque (local)
```bash
pip install -r requirements.txt
cp .env.example .env          # edita .env y pon tu ANTHROPIC_API_KEY
cd backend
uvicorn main:app --reload --port 8000
```
Abre http://localhost:8000

## Despliegue en Replit
- Sube la carpeta. En *Secrets* añade `ANTHROPIC_API_KEY` (no uses .env en Replit).
- Comando de ejecución: `cd backend && uvicorn main:app --host 0.0.0.0 --port 8080`

## Cómo probar
- **Salud:** `GET /api/health` → debe decir `"status": "ok"`.
- **Sin clave:** arranca sin `ANTHROPIC_API_KEY` → `/api/health` avisa del problema.
- **Análisis:** sube una foto de un taller/almacén con algún riesgo evidente
  (cable suelto, extintor tapado, falta de EPI) y comprueba los hallazgos.
- **Validación:** intenta subir un PDF o un archivo >5 MB → debe rechazarlo con
  mensaje claro.
- **Freemium:** tras 3 análisis, el 4º devuelve aviso de límite (borra la cookie
  `hs_free_used` para reiniciar en pruebas).

## Variables a configurar
| Variable | Dónde | Obligatoria |
|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` o Secrets | Sí |
| `MODEL_FREE` / `MODEL_PRO` | `config.py` | No (tienen valor por defecto) |
| `free_analyses_limit` | `config.py` | No (por defecto 3) |

## Qué NO incluye este MVP (y hace falta antes de cobrar)
- **Cuentas de usuario y base de datos.** El contador freemium es por cookie y
  se salta borrándola. Sin auth real no se puede facturar de forma fiable.
- **Pasarela de pago** (Stripe) y gestión de planes.
- **Persistencia** de análisis/informes.
- **Multi-imagen y anotación** de riesgos sobre la propia foto.
- **Validación humana en el flujo** (revisión por técnico antes de emitir informe).

Ver las notas del chat para las decisiones de modelo (Haiku vs. Sonnet) y los
riesgos legales del producto.
