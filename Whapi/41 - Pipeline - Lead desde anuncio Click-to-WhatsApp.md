---
tags: [whapi, pipeline, anuncios]
---

# Pipeline — Lead desde un anuncio Click-to-WhatsApp

## Evidencia (✅ `venta_bonsai.txt:65`)

> *"CASI TODOS LLEGAN DESDE UN ANUNCIO QUE YA LOS SALUDÓ ("¡Hola! Soy Eugenia, de Bonsái en
> Casa...") y que les deja escrito "Hola, quiero aprender las técnicas del Bonsái". Si su
> primer mensaje es ese o parecido, NO vuelvas a saludar largo ni te presentes."*

## Flujo

1. **Meta Ads** (cuenta `AD_ACCOUNT_ID`): campaña con objetivo *Interacción → Mensajes* o *Ventas*, destino **WhatsApp**, número +5492944508833.
2. En la **plantilla de mensaje** del anuncio (Message template / "Saludo"): texto de bienvenida "¡Hola! Soy Eugenia, de Bonsái en Casa…" + **mensaje precargado** "Hola, quiero aprender las técnicas del Bonsái".
3. La persona toca **Enviar mensaje** → se abre WhatsApp con el saludo del anuncio arriba y el texto precargado en la caja.
4. Envía → webhook con `referral` (`source_type: "ad"`, `source_id`, `ctwa_clid`) → [[14 - Webhooks de WhatsApp#3. Mensaje que viene de un anuncio Click-to-WhatsApp]].
5. Eugenia **no** se re-presenta; abre con una línea cálida ("¡Qué bueno que quieras aprender la técnica de verdad! 🌿") y **una** pregunta concreta.
6. Los mensajes que vienen de un anuncio CTWA abren una ventana de **72 h gratis** (punto de entrada gratuito) en lugar de 24 h. 🔵

## Medición

- Enganche medido en este número: pregunta concreta **73 %** vs "¿en qué te ayudo?" **57 %** ✅.
- Atribución: el link que manda Eugenia lleva `sck=wa-…` → Hotmart lo devuelve en `purchase.tracking.source_sck` ✅ (`config.sck`).
- 🔵 Con `ctwa_clid` se puede devolver la conversión a Meta (Conversions API para mensajería) para optimizar los anuncios por compra.
