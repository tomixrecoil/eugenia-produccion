---
tags: [whapi, meta]
---

# Meta — Business Manager, WABA y número

## Jerarquía de objetos en Meta

```
Business Manager (Portfolio comercial)  450083674862372  ✅ niches/*.yaml
├── Páginas de Facebook
│   ├── Ecosistema Hidropónico   615394648318530  ✅ niches/hidroponia.yaml
│   └── Bonsái en Casa           620810857774404  ✅ niches/bonsai.yaml  (producto: «Bonsai en casa desde cero»)
│        (cada una con su Instagram vinculado — publish_ig.get_ig_user_id)
├── Cuenta de WhatsApp Business (WABA)          → WHATSAPP_WABA_ID  ✅ config.py
│   └── Número +54 9 294 450-8833               → WHATSAPP_PHONE_ID ✅ config.py
├── Usuario de sistema (System User)           → genera WHATSAPP_TOKEN / META_TOKEN_KONTROL
├── Cuenta publicitaria                        → AD_ACCOUNT_ID / META_AD_ACCOUNT_ID
└── App de Meta for Developers «Kontrol»       → ver [[11 - Meta - App Kontrol]]
```

## Los tres identificadores de WhatsApp (✅ `config.py:192-194`)

| Variable | Qué es | Para qué se usa |
|---|---|---|
| `WHATSAPP_WABA_ID` | ID de la WhatsApp Business Account | Suscribir la app a los webhooks de la WABA (`POST /{waba-id}/subscribed_apps`), leer plantillas, número, calidad |
| `WHATSAPP_PHONE_ID` | **Phone Number ID** (no es el número: es un ID numérico largo) | Endpoint de envío `POST /{phone-number-id}/messages` y marcar leídos |
| `WHATSAPP_TOKEN` | Token de **usuario de sistema** (no vence) | Autoriza todo lo anterior **y** además llega a las 4 páginas de FB (se deriva el page token de cada una) |

> [!info] Por qué un solo token para todo (✅ `config.py:312-362`)
> `token_de_pagina()` llama a `GET /me/accounts?fields=id,access_token` con
> `WHATSAPP_TOKEN` y guarda el token de cada página en memoria. Así, conectar la página de
> bonsái ya no pisa la de hidroponía, y como el token es de sistema **no vence** (el page
> token "humano" vencía el 02/10/2026 por la regla de 90 días de acceso a datos).

## El número

- **+54 9 294 450-8833** — código de área 294 (San Carlos de Bariloche, Río Negro).
- Formato que espera la API: `5492944508833` (sin `+`, sin espacios). ✅ (`notify.py:154`, "Numero con codigo de pais, sin +")
- Aparece en todos los copys de los reels: `📲 Escríbeme por WhatsApp 👉 https://wa.me/5492944508833` ✅ (`prompts/gpt_copy.txt:134`, `hidroponia_gpt.txt:150`, `bonsai_gpt.txt:134`)
- Está registrado en **coexistencia**: el mismo número sigue abierto en la app WhatsApp Business del celular → [[13 - Coexistencia]].
- Un solo número atiende **dos productos** distintos; el Worker decide de qué nicho es cada charla → [[40 - Pipeline segundo a segundo - mensaje entrante#Paso 6 — Decidir el nicho de la charla]].

## Requisitos de Meta para tener esto (🔵)

1. Portfolio comercial **verificado** (Configuración del negocio → Centro de seguridad → Verificación). Sin verificar: límite de 250 conversaciones iniciadas por la empresa / 24 h y no se puede subir de nivel.
2. Nombre visible del número aprobado (display name).
3. Método de pago cargado en la WABA (las conversaciones de **marketing / utilidad** iniciadas con plantilla se cobran; las respuestas dentro de la ventana de 24 h a quien te escribió —*service*— son gratis).
4. App de Meta con el producto **WhatsApp** agregado → [[11 - Meta - App Kontrol]].

## Calidad y límites (🔵)

- **Calidad del número** (verde / amarillo / rojo) según bloqueos y reportes. Eugenia está diseñada para no ser invasiva (prohibido insistir con hardship genuino, prohibido urgencias falsas) en parte por esto. Ver [[71 - Seguridad y cumplimiento]].
- **Límite de mensajería**: cuántos clientes *nuevos* se pueden contactar por plantilla en 24 h (250 → 1K → 10K → 100K → ilimitado). Responder a quien escribió **no** consume este límite.
- En coexistencia el *throughput* de la API queda fijo en **20 mensajes/segundo**.
