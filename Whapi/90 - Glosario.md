---
tags: [whapi, glosario]
---

# Glosario

| Término | Significado |
|---|---|
| **WABA** | WhatsApp Business Account: la cuenta que agrupa números, plantillas y facturación |
| **Phone Number ID** | ID numérico interno del número en la API (≠ el número de teléfono) |
| **Cloud API** | La API de WhatsApp alojada por Meta (`graph.facebook.com/{v}/{phone_id}/messages`) |
| **Coexistencia** | El mismo número funcionando a la vez en la app WhatsApp Business y en la Cloud API |
| **Eco (`smb_message_echoes`)** | Webhook que avisa que el negocio mandó un mensaje desde la app del celular |
| **wamid** | ID único de un mensaje de WhatsApp |
| **Ventana de 24 h** | Período tras el último mensaje del cliente en que se puede responder con texto libre |
| **Plantilla (template)** | Mensaje pre-aprobado por Meta, necesario para escribir fuera de la ventana |
| **CTWA** | Click-to-WhatsApp: anuncio que abre un chat; trae `referral` y ventana gratis de 72 h |
| **Usuario de sistema** | Usuario "robot" del portfolio cuyo token no vence |
| **App Kontrol** | La app de Meta for Developers del negocio (permisos, webhooks, token de respaldo) |
| **Worker** | Función serverless de Cloudflare (JS) que corre en el borde, 24/7 |
| **R2** | Almacenamiento de objetos de Cloudflare (bucket `marketing-reels`) |
| **wrangler** | CLI de Cloudflare para desplegar Workers y manejar R2/secretos |
| **Puerta R2** | Worker `eugenia-puerta-r2`: acceso limitado a R2 para GitHub (y `/whisper`) |
| **Bóveda** | `panel/boveda_produccion.json`: credenciales cifradas en R2 para la producción en la nube |
| **Groq** | Proveedor de inferencia LLM rápido (API compatible con OpenAI) |
| **Reglas post / ctx** | Correcciones por código a la respuesta del LLM (`post_*`) o contexto que se le agrega antes (`ctx_*`) |
| **`[SITUACIÓN]`** | Bloque dinámico que el Worker agrega al prompt según el momento de la charla |
| **sck** | Parámetro de Hotmart para atribuir el origen de una venta (`wa-…`, `ig-r-…`, `fb-r-…`) |
| **hottok** | Token que Hotmart manda en sus webhooks para validar que son legítimos |
| **Stock** | Reels ya producidos esperando en R2 para publicarse sin la PC |
| **Nicho** | Producto/vertical: `hidroponia`, `bonsai` (y `numerologia` en preparación) |
| **Modo dueño** | Órdenes que Tomix le da a Eugenia por WhatsApp |
