---
tags: [whapi, metodologia]
---

# Fuentes y nivel de certeza

Esta documentación se armó leyendo **todo** el código de los tres repositorios que hay en
GitHub (`eugenia-produccion`, `eugenia-carritos`, `sylvana-jarvis`) al 01/11/2026, y se actualizó con el
export nuevo de `eugenia-produccion` del 04/11/2026 (commits `167545e` y `7c00018`).

> [!warning] Lo que NO estaba disponible
> El código fuente del **Worker de Cloudflare que atiende WhatsApp** (carpeta
> `marketing-agent/cloudflare-worker/`), el **panel web** (`webapp.py`) y el resto de
> `marketing-agent` **viven solo en la PC Windows "MYX"** y no están subidos a GitHub.
> `eugenia-produccion` es una *copia parcial* de `marketing-agent` (lo dice su README).
> Por eso, todo lo que pasa *dentro* del Worker se reconstruyó a partir de:
> - comentarios y llamadas en el código Python que habla con el Worker,
> - los prompts de venta de Eugenia (`prompts/venta_*.txt`), que son lo que el Worker le manda al modelo,
> - las claves de R2 y endpoints que el código nombra,
> - y el funcionamiento oficial de la WhatsApp Cloud API / Cloudflare Workers.
>
> Ver [[99 - Pendientes de documentar]] para cerrar esos huecos.

## Leyenda (se usa en todas las notas)

| Marca | Significa |
|---|---|
| ✅ **Verificado** | Está escrito en el código o la config de los repos. Se cita archivo y línea. |
| 🟡 **Deducido** | Lo afirma un comentario del código o se desprende sin dudas de él, pero el código que lo ejecuta no está en los repos. |
| 🔵 **Estándar** | Así funciona la plataforma (Meta / Cloudflare / Groq / Hotmart). Es como *hay que* hacerlo para replicar; el detalle exacto de tu implementación puede variar. |
| ❓ **Sin confirmar** | Hipótesis razonable. Verificar en la PC antes de confiar. |

## Archivos que aportaron evidencia

| Archivo | Qué aporta |
|---|---|
| `eugenia-produccion/config.py` | Lista completa de secretos (`ENV_KEYS`), token de sistema, app **Kontrol**, Groq, hottok, `PANEL_KEY`, `sck()` (origen `wa-…`), derivación de tokens de página |
| `eugenia-produccion/prompts/venta_hidroponia.txt` · `venta_bonsai.txt` | El *system prompt* de Eugenia en WhatsApp, con sus placeholders `{{PRECIO}}`, `{{QUE_INCLUYE}}`, `{{DATOS_COBRO}}`, `[SITUACIÓN]` |
| `eugenia-produccion/prompts/*_reglas.json` | Los interruptores de las reglas de post-proceso de las respuestas |
| `eugenia-produccion/prompts/bonsai_incluye_ar.txt` / `bonsai_producto.md` | El texto fijo "QUÉ INCLUYE" |
| `eugenia-produccion/parametros_ia.json` | Modelos y temperatura de Groq y Gemini |
| `eugenia-produccion/src/notify.py` | Envío real de WhatsApp por Cloud API (`/{phone_id}/messages`), ventana de 24 h, error 131047 |
| `eugenia-produccion/src/publish.py` / `src/publisher.py` | Botón "Enviar mensaje de WhatsApp" en los reels, cola de Instagram en R2, cron del Worker cada 10 min |
| `eugenia-produccion/src/toggles.py` | `state/toggles.json` que lee el Worker (encolado y horarios) |
| `eugenia-produccion/armar_stock.py` | URL del Worker, ruta pública `/v/`, guard contra `wa/clientes.json`, órdenes del dueño a Eugenia |
| `eugenia-produccion/r2io.py` | Worker `eugenia-puerta-r2` (cabecera `x-clave`) |
| `eugenia-produccion/registro_fuentes.py` | "Eugenia tiene que poder consultar el registro desde WhatsApp" |
| `eugenia-produccion/producir_stock.py` | Comentar CULTIVO/BONSAI → link por privado (lo hace el Worker) |
| `eugenia-produccion/src/pipeline.py` | XTTS local = voz de Eugenia (clon de Sylvana) |
| `eugenia-carritos/*` | Worker `eugenia-mail-recuperacion`, `/ingest`, cron 8 am |
| `eugenia-produccion/r2io.py` (04/11) | Bóveda cifrada `panel/boveda_produccion.json`, `state/nichos/*.yaml` |
| `eugenia-produccion/subir_youtube_nube.py` (04/11) | `stock/publicados.json` lo anota el Worker; `stock/youtube.json`; interruptor `yt` |
| `eugenia-produccion/src/toggles.py` (04/11) | Interruptores `fb`/`ig`/`yt`; nombre real de la función del Worker: `publicarDeStock` |
| `eugenia-produccion/src/voz_charon.py` (04/11) | Ruta `/whisper` de la puerta R2 (Whisper de Cloudflare) |
| `sylvana-jarvis/*` | **No participa** del WhatsApp (asistente de voz / trading). Solo lo nombra como integración futura en el PRD. |
