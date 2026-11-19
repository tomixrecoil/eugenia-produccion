---
tags: [whapi, seguridad, configuracion]
---

# Secretos y variables

> [!danger] Nunca pegues valores reales en este vault
> Acá solo van **nombres** y **para qué sirven**. Los valores viven en el `.env` de la PC
> (con backups `.env.bak_<fecha>`), en los secretos del Worker y en los secretos de GitHub.

## Dónde vive cada cosa

| Lugar | Cómo se edita |
|---|---|
| `.env` de `marketing-agent` (PC) | Panel → pestaña **Credenciales** (`config.write_env`: fusiona, backup, escritura atómica) |
| Secretos del Worker | `npx wrangler secret put <NOMBRE>` desde `cloudflare-worker/` |
| Secretos de GitHub | Repo → Settings → Secrets and variables → Actions |

## Todas las variables relacionadas con WhatsApp / Eugenia (✅ `config.py:625-698`)

| Variable | Dónde | Uso |
|---|---|---|
| `WHATSAPP_TOKEN` | .env + Worker | Token de sistema: enviar/recibir, derivar page tokens |
| `WHATSAPP_PHONE_ID` | .env + Worker | Phone Number ID del +5492944508833 |
| `WHATSAPP_WABA_ID` | .env + Worker | ID de la WABA |
| `META_TOKEN_KONTROL` | .env | Token de sistema de la app Kontrol (respaldo) |
| `META_APP_ID`, `META_APP_SECRET` | .env (+ Worker 🟡) | Firma de webhooks, debug de tokens |
| `META_GRAPH_VERSION` | .env | Default `v21.0` |
| `META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN` | .env | Página y token de fallback |
| `GROQ_API_KEY`, `_2`, `_3` | Worker (+ .env desde 29/08) | LLM de Eugenia, 3 cuentas para sumar cupo |
| `PANEL_KEY` | .env + Worker | Autoriza endpoints protegidos del Worker |
| `ALIAS_AR`, `MONTO_AR`, `CBU_AR`, `BANCO_AR` | .env + Worker | Cobro por transferencia en Argentina fuera de Hotmart. **Si falta alguno, Eugenia no lo ofrece** |
| (datos de Western Union) | Worker / prompt | `{{DATOS_COBRO}}` para Venezuela ❓ nombre de variable |
| `HOTMART_CLIENT_ID`, `_SECRET`, `HOTMART_BASIC` | .env + GitHub | Verificar compras antes de reenviar accesos; carritos |
| `HOTMART_HOTTOK` | Worker | Validar webhooks de la cuenta principal |
| `HOTMART_HOTTOK_NUMEROLOGIA` | Worker | Validar webhooks de la 2da cuenta (Sersoular) |
| `ALERT_WHATSAPP` | .env | Número de Tomix (con código de país, sin `+`) para alertas |
| `ALERT_EMAIL`, `GMAIL_ECOSISTEMA_USER/PASS` | .env | Alertas por mail (apagadas por default desde 01/11: `AVISOS_MAIL=1` para prender) |
| `ELEVEN_SYLVANA_KEY` | .env | Voz clonada de Sylvana para notas de voz |
| ~~`XTTS_PUERTOS`~~ | — | Sacado de `ENV_KEYS` el 02/11/2026 (XTTS local ya no figura en el export) |
| `BOVEDA_KEY`, `BOVEDA_PRODUCCION_KEY` | .env (+ secreto GitHub `BOVEDA_PRODUCCION_KEY`) | Abrir la bóveda de credenciales en R2 (`boveda.py`) |
| `PUERTA_R2_KEY` | .env + GitHub | Clave de la puerta R2 (también abre `/whisper`). En la PC va **sin** `PUERTA_R2_URL`, si no `r2io` cree que está en la nube |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_<NICHO>` | .env → bóveda | Subida a YouTube desde GitHub (un permiso por canal; bonsái todavía sin canal) |
| `EMBUDO_TZ` | .env | Zona horaria para cortar "hoy/semana" en el embudo |
| `ANTHROPIC_API_KEY` | .env | Asistencia con Claude Code |

## Secretos de GitHub

| Repo | Secretos |
|---|---|
| `eugenia-carritos` | `HOTMART_CLIENT_ID`, `HOTMART_CLIENT_SECRET`, `HOTMART_BASIC`, `WORKER_URL`, `MAIL_KEY` |
| `eugenia-produccion` | `PUERTA_R2_KEY`, `BOVEDA_PRODUCCION_KEY`, `GEMINI_MODEL`, `GEMINI_API_KEY` … `_6`, `ELEVENLABS_API_KEY` … `_5`; **variable** `PUERTA_R2_URL` |
