---
tags: [whapi, contexto, ia]
aliases: [Briefing Whapi, Memoria Whapi]
---

# Contexto para Claude — Whapi en una página

> **Whapi es el proyecto más importante de Tomix.** Cualquier Claude (Code, VS Code,
> Chrome, navegador, claude.ai) que trabaje con él tiene que leer esta nota primero.
> **Fuente canónica: repo `tomixrecoil/eugenia-carritos`, carpeta `Whapi/`** (vault de
> Obsidian; ese repo no se regenera). Copias: `eugenia-produccion/Whapi/` (se borra cada vez
> que corre `exportar_produccion.py`: volver a copiarla), `sylvana-jarvis/docs/Whapi/`,
> Notion ([página Whapi](https://app.notion.com/p/40b5314feb14811998b6f2efd27d4640) + memoria
> [Whapi](https://app.notion.com/p/40b5314feb1481b089f9e599a56752a4)) y Google Drive
> ([carpeta Whapi](https://drive.google.com/drive/folders/1PxsigA6ZAx83L9TqKoM9Gs-m4F65mrA0) →
> "Whapi - Resumen, pipeline y guía para replicar" + "Whapi - Documento completo - Parte 1..4"). En cada repo: `CLAUDE.md` + skill `.claude/skills/whapi/`.

## Qué es

El WhatsApp del negocio **+54 9 294 450-8833** (`5492944508833`, Bariloche) atendido
automáticamente por **Eugenia**, asesora de ventas con nombre humano, para dos productos:

| Nicho | Negocio | Producto | Checkout Hotmart | Página FB |
|---|---|---|---|---|
| `hidroponia` | Ecosistema Hidropónico | Curso Completo de Hidroponía (+32 h) | `W99083833C` | `615394648318530` |
| `bonsai` | Bonsái en Casa | Bonsai en casa desde cero (antes «El Arte del Bonsái»; +6 h, 3 cursos en 1) | `T97313346W` (landing `conocimientosdigital.com/bonsai/`) | `620810857774404` |

Portfolio comercial (Business Manager): `450083674862372`. Descuento por nicho: 80 % (solo si dicen "caro").

## Arquitectura (de memoria)

```
Cliente → WhatsApp Cloud API (número en COEXISTENCIA con la app WhatsApp Business del celular de Tomix)
       → webhook de la app de Meta (Kontrol u otra) → Worker Cloudflare marketing-ig-scheduler (= Eugenia)
       → R2 marketing-reels (wa/clientes.json, historial) → prompt venta_<nicho>.txt + [SITUACIÓN]
       → Groq (gpt-oss-20b → qwen3.6-27b → compound-mini; 3 cuentas; temp 0.7; 700 tokens)
       → reglas post_* (formato, precio exacto, link aparte, sck=wa-…) → POST /{phone_id}/messages
```

- **Workers** (`*.goldentimeshift.workers.dev`): `marketing-ig-scheduler` (Eugenia + cron c/10 min de publicación IG + `/v/` videos + `/wa-groq?listar=1` + webhooks IG/Hotmart + endpoints con `PANEL_KEY`), `eugenia-mail-recuperacion` (`/ingest` + cron 8 am, carritos), `eugenia-puerta-r2` (acceso limitado a R2 para GitHub, cabecera `x-clave`).
- **R2 `marketing-reels`**: `wa/…` (sensible), `queue/<fecha>.json`, `reels/<id>.mp4`, `stock/index.json`, `state/toggles.json`, `fuentes/usadas.json`, `mail/lista.json`.
- **App Meta «Kontrol»**: token de sistema `META_TOKEN_KONTROL` (29/08/2026) con permisos amplios; es **respaldo**, NO reemplaza a `WHATSAPP_TOKEN` sin confirmación de Tomix.
- **Tokens**: `WHATSAPP_TOKEN` = usuario de sistema, no vence, también deriva page tokens (`config.token_de_pagina`). `WHATSAPP_PHONE_ID`, `WHATSAPP_WABA_ID`, `META_APP_SECRET`.
- **Bóveda de credenciales** (02/11/2026): `panel/boveda_produccion.json` en R2, cifrada AES-GCM; GitHub la abre con `BOVEDA_PRODUCCION_KEY` (`r2io.cargar_credenciales`). Los ajustes de nicho del panel viajan a `state/nichos/<nicho>.yaml`.
- **Interruptores por nicho** en `state/toggles.json`: `produccion`, `encolado`, `fb`, `ig`, `yt`, `horas`. El Worker (`publicarDeStock`) los respeta y anota lo publicado en `stock/publicados.json`.
- **PC Windows "MYX"**: `marketing-agent/` (código real del Worker en `cloudflare-worker/`, panel `webapp.py`, `.env`). **No está en GitHub.**
- **GitHub Actions**: 01:00 catalogar fuentes, 02:00 producir reels, 07:00 carritos (ART).
- **Coexistencia**: Tomix ve y contesta desde el celular; sus mensajes llegan como `smb_message_echoes`. La app debe abrirse cada ≤14 días. 20 msg/s.
- **Alertas** al dueño: `notify.py` → Cloud API a `ALERT_WHATSAPP`; si no le escribió al número en 24 h, error 131047 llega por webhook aunque el POST dé 200.

## Reglas de Eugenia que NUNCA se rompen

- Precio **exacto** con centavos (`{{PRECIO}}` USD, pago único). Sin urgencias, cupos ni "gratis".
- Link solo, en su renglón, al final (para la tarjeta de preview); nunca `[texto](url)`; uno por mensaje.
- Español neutro, sin voseo ni argentinismos; 3–4 líneas, < 500 caracteres; 1–3 emojis; sin negritas.
- Nunca "¿en qué te ayudo?" (57 % vs 73 % con pregunta concreta). Nunca usar un nombre que el cliente no dio.
- No inventar nada fuera de "QUÉ INCLUYE". Hardship genuino → despedida cálida sin link.
- Datos de cobro solo los oficiales (anti-fraude). Venezuela → Western Union. Argentina → transferencia (ALIAS/CBU/BANCO/MONTO, solo si están los 4).

## Cómo trabajar en Whapi (para cualquier Claude)

1. Leer `Whapi/00 - Inicio.md` y la nota que corresponda. Respetar la leyenda ✅/🟡/🔵/❓ de `02 - Fuentes y nivel de certeza.md`.
2. **Todo cambio** al sistema se documenta en el vault en el mismo trabajo (y se actualiza esta nota si cambia algo de arriba). Si algo pasa de ❓ a ✅, cambiar la marca.
3. Nunca escribir valores de secretos en el vault, en commits ni en Notion/Drive: solo nombres.
4. El código de referencia probado está en `Whapi/codigo/worker-referencia` (`npm test`).
5. Huecos abiertos: `99 - Pendientes de documentar.md` (requiere el código de `marketing-agent`).
6. `eugenia-produccion` se regenera con `exportar_produccion.py` (pasó el 04/11/2026 y borró `Whapi/`): editar siempre la copia de `eugenia-carritos` y desde ahí copiar a los demás. Arreglo definitivo pendiente: que `exportar_produccion.py` conserve `Whapi/`, `CLAUDE.md` y `.claude/`.
