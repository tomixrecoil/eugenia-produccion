---
tags: [whapi, cloudflare, worker, backend]
aliases: [Worker Eugenia]
---

# Worker `marketing-ig-scheduler` — el backend de Eugenia

URL: `https://marketing-ig-scheduler.goldentimeshift.workers.dev` ✅

## Responsabilidades

| # | Qué hace | Disparador | Certeza |
|---|---|---|---|
| 1 | **Atiende el WhatsApp** (recibe mensajes, arma prompt, llama a Groq, contesta) | Webhook de Meta | 🟡 (prompts con `{{…}}` que solo puede rellenar el Worker; Groq "solo como secreto de Cloudflare"; `/wa-groq`) |
| 2 | Rotación y diagnóstico de las 3 cuentas de Groq | Endpoint `/wa-groq?listar=1` | ✅ nombre del endpoint (`config.py:638`) |
| 3 | Guarda clientes y conversaciones en R2 (`wa/clientes.json` y afines) | Cada mensaje | ✅ clave citada (`armar_stock.py:108`) |
| 4 | **Modo dueño**: Tomix le da órdenes por WhatsApp ("stock", "publicá uno de bonsái", consultar fuentes) | Mensaje desde el número del dueño | ✅ (`armar_stock.py:17`, `registro_fuentes.py:48`) → [[33 - Eugenia - Modo dueño]] |
| 5 | **Cron cada 10 min**: publica en Instagram lo que vence en `queue/<fecha>.json` (`publish_at`) | Cron Trigger | ✅ (`publisher.py:772-777`) |
| 6 | Publica del **stock** a las horas del nicho (default 6 y 18 ART) si `encolado` está prendido, **solo en las redes con su interruptor prendido** (`fb`, `ig` en `state/toggles.json`). Función `publicarDeStock`. Anota cada publicación en `stock/publicados.json` (de ahí sale la subida a YouTube) | Cron | ✅ (`toggles.py` 04/11, `subir_youtube_nube.py`) |
| 7 | Ruta pública **`/v/reels/<id>.mp4`** para que Instagram descargue el video | GET | ✅ (`armar_stock.py:47,105-108`) |
| 8 | **Comentario en IG con la palabra** (CULTIVO / BONSAI) → manda el link por privado | Webhook de Instagram | ✅ (`producir_stock.py:596-601`) → [[42 - Pipeline - Comentario en Instagram a mensaje privado]] |
| 9 | Recibe **webhooks de Hotmart** (validados con `hottok`) de las dos cuentas | Webhook Hotmart | ✅ claves (`config.py:648-655`) |
| 10 | Endpoints protegidos para el **panel** (clave `PANEL_KEY`) | HTTP | ✅ (`config.py:626-629`) |

## Rutas conocidas y probables

| Ruta | Método | Para qué | Certeza |
|---|---|---|---|
| `/v/<reels/archivo.mp4>` | GET | Servir videos públicos. **Guard**: solo prefijo `reels/` y nombre plano, para que nadie pueda pedir `wa/clientes.json` por ahí | ✅ |
| `/wa-groq?listar=1` | GET | Ver estado / cupo de las cuentas de Groq | ✅ |
| `/<webhook WA>` | GET/POST | Verificación + mensajes de Meta | 🔵 (ruta exacta ❓) |
| `/<webhook IG>` | GET/POST | Comentarios de Instagram | 🟡 |
| `/<webhook hotmart>` | POST | Ventas (valida `X-HOTMART-HOTTOK`) | 🟡 |
| `/api/*` con `PANEL_KEY` | varios | Panel web | 🟡 |

## Secretos del Worker (`wrangler secret put …`)

✅ Citados explícitamente como "secretos de Cloudflare": `GROQ_API_KEY`, `GROQ_API_KEY_2`,
`GROQ_API_KEY_3`, `HOTMART_HOTTOK`, `HOTMART_HOTTOK_NUMEROLOGIA` (`config.py:636-655`,
"WORKER_SECRET_KEYS ya lo tenía").

🟡 Necesarios por lo que hace: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_WABA_ID`,
`META_APP_SECRET`, token de verificación del webhook, `PANEL_KEY`, `ALIAS_AR`, `MONTO_AR`,
`CBU_AR`, `BANCO_AR`, datos de Western Union, número del dueño.

> En la PC existe una lista `WORKER_SECRET_KEYS` (en `marketing-agent`, ✅ mencionada en
> `config.py:649`) con las claves del `.env` que se copian como secretos al Worker.

## Disparadores

```toml
# wrangler.toml (🔵 forma; valores ✅ del código)
name = "marketing-ig-scheduler"
main = "src/index.js"
compatibility_date = "2026-01-01"

[[r2_buckets]]
binding = "R2"
bucket_name = "marketing-reels"

[triggers]
crons = ["*/10 * * * *"]   # ✅ "corre su propio cron cada 10 min" (publisher.py:772)
```

Implementación de referencia completa → [[61 - Código de referencia - Worker WhatsApp]].
