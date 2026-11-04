---
tags: [whapi, frontend]
---

# Frontend — Panel web (`webapp.py`, PC)

El "frontend" del sistema es un **panel web local** que corre en la PC (`marketing-agent/webapp.py`,
no disponible en GitHub). Todo lo que sigue sale de referencias en el código ✅ salvo indicación.

## Pestañas / secciones conocidas

| Sección | Qué se hace | Evidencia |
|---|---|---|
| **Nicho** / Ajustes → *Mi producto* | Fuentes, link de venta con switch **landing ↔ checkout**, nombre de producto y negocio, % de descuento, publicación, horarios | `config.py:108-132,732-737` |
| **Credenciales** | Editar el `.env` (tokens WhatsApp, Kontrol, Groq, Hotmart, cobro AR…). Botón "+" para sumar cuentas Gemini/ElevenLabs. Escribe con `write_env` (fusión + backup + atómico) | `config.py:784-944` |
| **Prompts** → nicho | Editar `venta_<nicho>.txt` (Eugenia), "Descripción del producto" (`{{QUE_INCLUYE}}`), prompts de voz y copy | `venta_*.txt:76` |
| **Reglas** | Prender/apagar `post_*` por nicho (`<nicho>_reglas.json`) | [[32 - Eugenia - Reglas post-proceso]] |
| **Subtítulos** | Mapa palabra=emoji, karaoke, pop-in, colores | `config.py:45-47,165-171` |
| **Salud** | Latidos (`state/*_heartbeat.json`: >3 min amarillo, >10 gris), estado de lo que corre (los mails de aviso se apagaron en favor de esto) | `producir_stock.py:69-81`, `notify.py:245-247` |
| **Embudo** | Leads → conversaciones → link → venta, cortado por "hoy/semana" en `EMBUDO_TZ` | `config.py:679-680` |
| **Ventas** | Ventas de Hotmart (las sube la PC; desde GitHub Hotmart da 403) | commits `739ec2e`, `a222552` |
| **Gasto en anuncios** | Con `META_ADS_TOKEN` / `META_AD_ACCOUNT_ID` | `config.py:690-691` |
| **Producción / encolado** | Toggles por nicho y horas de publicación → `state/toggles.json` en R2 | `src/toggles.py` |
| **Notas de voz** | Generar con la voz clonada de Sylvana | `config.py:677-678` |
| **Conexión Meta** | `/api/meta/connect` guarda el page token | `config.py:318-319` |
| Publicar | `/api/publicar-uno`, `/api/publish` | `publisher.py` docstring |

## Cómo habla con la nube

- Con R2: `npx wrangler r2 object …` (login de Tomix).
- Con el Worker: HTTP con `PANEL_KEY` (si falta, 401 — ya pasó, por eso se agregó a `ENV_KEYS`).
- Con Meta: Graph API directo con los tokens del `.env`.

## Para replicar (🔵)

Cualquier framework sirve (el original es Python). Lo mínimo útil para operar Eugenia:
editor del prompt y reglas (guardando en R2 para que el Worker los lea), lista de
conversaciones con botón **Pausar/Reanudar bot** por contacto, y vista del embudo.
