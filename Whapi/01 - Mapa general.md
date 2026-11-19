---
tags: [whapi, arquitectura]
---

# Mapa general de la arquitectura

## En una frase

Una persona le escribe al **+54 9 294 450-8833** → los servidores de Meta (WhatsApp
**Cloud API**, número en **coexistencia** con la app WhatsApp Business del celular) le
mandan un **webhook** a la app de Meta (**Kontrol**) → ese webhook apunta a un **Worker de
Cloudflare** → el Worker carga la conversación desde **R2**, arma el *prompt* de venta de
**Eugenia**, le pregunta a **Groq** (LLM), limpia la respuesta con las **reglas** →
la manda con `POST /{phone-number-id}/messages` → el mensaje aparece en el WhatsApp del
cliente **y también** en la app WhatsApp Business del celular de Tomix.

## Diagrama

```mermaid
flowchart LR
  subgraph Cliente
    U[📱 Lead / cliente]
  end
  subgraph Meta
    WA[(WhatsApp\nCloud API)]
    APP[App Meta Developers\n«Kontrol»\nwebhooks + tokens]
    BIZ[📱 WhatsApp Business App\ncelular de Tomix\n(coexistencia)]
    ADS[Anuncios Click-to-WhatsApp\n+ botón WA en reels]
    IG[Instagram / Facebook]
  end
  subgraph Cloudflare
    W1[Worker\nmarketing-ig-scheduler\n= Eugenia]
    W2[Worker\neugenia-mail-recuperacion]
    W3[Worker\neugenia-puerta-r2]
    R2[(R2 bucket\nmarketing-reels)]
    CRON1((cron c/10 min))
    CRON2((cron 8 am ART))
  end
  subgraph IA
    GROQ[Groq\ngpt-oss-20b → qwen3.6-27b → compound-mini]
    GEM[Gemini\n(reels / copys)]
  end
  subgraph PC[PC Windows «MYX» — marketing-agent]
    PANEL[Panel web\nwebapp.py]
    TAREAS[Tareas programadas\nmonitor ventas, vigilancia]
    WR[wrangler CLI]
  end
  subgraph GitHub
    GH1[Actions: Producir reels 02:00]
    GH2[Actions: Catalogar fuentes 01:00]
    GH3[Actions: Carritos 07:00]
  end
  HOT[Hotmart]

  U -- escribe --> WA
  ADS -- abre chat --> U
  WA -- webhook POST --> APP --> W1
  W1 <--> R2
  W1 -- prompt --> GROQ
  W1 -- POST /messages --> WA --> U
  WA <-. sync / echoes .-> BIZ
  BIZ -- Tomix contesta a mano --> WA
  IG -- webhook comentario --> W1
  W1 -- DM con link --> IG
  CRON1 --> W1
  W1 -- publica reels IG/FB --> IG
  HOT -- webhook venta (hottok) --> W1
  GH3 -- POST /ingest --> W2 --> R2
  CRON2 --> W2
  GH1 & GH2 -- x-clave --> W3 --> R2
  PANEL -- PANEL_KEY --> W1
  WR --> R2
  TAREAS -- alertas Cloud API --> WA
```

## Las piezas y su rol

| Pieza | Rol | Nota |
|---|---|---|
| Número `+5492944508833` | Línea única de atención y ventas para los dos productos | [[10 - Meta - Business Manager, WABA y número]] |
| WhatsApp Business App (celular) | Sigue funcionando en paralelo: Tomix ve todo y puede intervenir | [[13 - Coexistencia]] |
| WABA + Cloud API | La "puerta programática" del número | [[10 - Meta - Business Manager, WABA y número]] |
| App **Kontrol** (Meta for Developers) | Contenedor de permisos, webhooks y token de sistema | [[11 - Meta - App Kontrol]] |
| Worker `marketing-ig-scheduler` | El backend de Eugenia: webhook WA, IG, Hotmart, cron de publicación, endpoints del panel | [[21 - Worker marketing-ig-scheduler (Eugenia)]] |
| R2 `marketing-reels` | La "base de datos": clientes, conversaciones, colas, stock, toggles | [[24 - R2 - Mapa de claves]] |
| Groq | Genera cada respuesta de Eugenia | [[30 - Eugenia - Cerebro y modelos]] |
| Prompts `venta_<nicho>.txt` | Personalidad, producto, método de venta, reglas duras | [[31 - Eugenia - Prompt de venta]] |
| Reglas post-proceso | Arreglan la respuesta antes de mandarla (link, precio, formato) | [[32 - Eugenia - Reglas post-proceso]] |
| Panel web (PC) | Editar prompts, reglas, nichos, credenciales; ver embudo, salud, ventas | [[50 - Frontend - Panel web]] |
| GitHub Actions | Producción de reels y carritos abandonados con la PC apagada | [[52 - GitHub Actions]] |
| Hotmart | Cobro, webhooks de venta, carritos abandonados | [[43 - Pipeline - Carritos abandonados]] |

## Principios de diseño que se repiten en todo el sistema

1. **Que funcione con la PC apagada.** Todo lo que atiende clientes vive en Cloudflare; la PC solo edita y produce. ✅ (`armar_stock.py`, `r2io.py`, `README` de carritos)
2. **R2 es la fuente de verdad**, no el disco. ✅ (`registro_fuentes.py:48`, `toggles.py`)
3. **Una sola fuente por dato**: el link de venta sale de `config.checkout()`; los nichos activos de `nichos_produccion()`. ✅
4. **Cada link de venta lleva su origen** (`sck=wa-…`, `ig-r-…`, `fb-r-…`) para saber qué canal vendió. ✅ (`config.sck`)
5. **Mínimo privilegio**: la nube (GitHub) nunca ve `wa/clientes.json`; pasa por la "puerta". ✅ (`r2io.py`)
6. **Nunca mentir en precio ni urgencia**; Eugenia no inventa descuentos ni cupos. ✅ (prompts)
