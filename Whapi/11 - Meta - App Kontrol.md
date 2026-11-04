---
tags: [whapi, meta, app]
aliases: [Kontrol, Claude Kontrol]
---

# Meta — App «Kontrol» (Meta for Developers)

## Qué es

Una **app de Meta for Developers** (developers.facebook.com → Mis apps) llamada **Kontrol**.
En Meta, una "app" no es algo que se instala: es el **contenedor de permisos y webhooks**
a través del cual un sistema externo (acá, los Workers y la PC) habla con las APIs de
WhatsApp, Instagram, Páginas y Ads.

✅ Evidencia (`config.py:663-667`):

> *Token de sistema de la app de Meta "Kontrol" (29/08). Permisos amplios (WhatsApp,
> Instagram, Ads, paginas) — candidato fuerte a reemplazar WHATSAPP_TOKEN si ese se cae,
> pero NO se pisa el que ya esta en produccion sin que Tomix lo confirme: lo usan todas
> las conversaciones activas. Guardado aparte hasta que diga para que va.*
> → variable `META_TOKEN_KONTROL`

## Rol de Kontrol en el sistema

| Función | Detalle | Certeza |
|---|---|---|
| Emisor del token de sistema "amplio" | `META_TOKEN_KONTROL`, con WhatsApp + Instagram + Ads + Páginas | ✅ |
| Respaldo del token de producción | Reemplazo previsto de `WHATSAPP_TOKEN` si este se cae; **todavía no en uso** al 01/11/2026 | ✅ |
| Credenciales de app | `META_APP_ID` / `META_APP_SECRET` (`config.py:187-188`) — el *App Secret* firma los webhooks (`X-Hub-Signature-256`) | ✅ claves / 🔵 uso |
| Suscripción de webhooks | Producto WhatsApp → Configuración → URL de callback = Worker + token de verificación; campos `messages` (y en coexistencia `smb_message_echoes`, `history`, `smb_app_state_sync`) | 🔵 |
| Login/Embedded Signup de coexistencia | La app es la que hace el *onboarding* del número en coexistencia | 🔵 |
| Instagram | Webhooks de comentarios para el flujo "Comenta CULTIVO" → [[42 - Pipeline - Comentario en Instagram a mensaje privado]] | 🟡 |

> [!question] ¿Kontrol es la app que hoy recibe los webhooks de WhatsApp?
> El código solo dice que su token es un **respaldo**. El token en producción
> (`WHATSAPP_TOKEN`) es de un usuario de sistema que podría haber sido generado con
> **otra** app. Verificar en developers.facebook.com → Kontrol → WhatsApp → Configuración
> si la URL de callback apunta al Worker. Ver [[99 - Pendientes de documentar]].

## Cómo se crea una app como Kontrol (🔵 paso a paso)

1. developers.facebook.com → **Mis apps → Crear app**.
2. Caso de uso: **Otro** → Tipo: **Empresa (Business)**. Nombre: `Kontrol`. Vincularla al portfolio `450083674862372`.
3. En el panel de la app → **Agregar producto → WhatsApp → Configurar**. Elegir la WABA del negocio.
4. **Configuración de la app → Básica**: copiar **ID de la app** (`META_APP_ID`) y **Clave secreta** (`META_APP_SECRET`). Completar URL de política de privacidad, ícono, categoría.
5. **WhatsApp → Configuración → Webhook**:
   - URL de devolución de llamada: `https://<worker>.workers.dev/<ruta-webhook>`
   - Token de verificación: un string inventado (secreto del Worker, p. ej. `WA_VERIFY_TOKEN`).
   - **Administrar campos** → suscribir `messages`. En coexistencia además `smb_message_echoes`, `history`, `smb_app_state_sync`.
6. (Si hace falta) **Agregar producto → Instagram** (comentarios / mensajes) y **Webhooks → Page** (`feed`) / **Instagram** (`comments`, `messages`).
7. Pasar la app a **modo Activo (Live)**. En modo desarrollo solo llegan webhooks de usuarios con rol en la app.
8. **Revisión de la app**: para `whatsapp_business_messaging`, `whatsapp_business_management`, `instagram_manage_comments`, `instagram_manage_messages`, `pages_manage_posts`, `ads_read`… con **Acceso avanzado** cuando se usan con activos de terceros. Si todos los activos son del mismo portfolio que es dueño de la app, alcanza con acceso estándar + usuario de sistema.
9. Generar el **token de sistema** → [[12 - Meta - Tokens y permisos]].
10. Suscribir la app a la WABA: `POST https://graph.facebook.com/v21.0/{WABA_ID}/subscribed_apps` con el token. (Sin esto la WABA **no** manda webhooks a la app aunque esté todo configurado.)
