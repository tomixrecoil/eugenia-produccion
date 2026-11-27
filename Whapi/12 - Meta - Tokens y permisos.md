---
tags: [whapi, meta, seguridad]
---

# Meta — Tokens y permisos

## Inventario de tokens (✅ `config.py`)

| Variable | Tipo | Vence | Lo usa |
|---|---|---|---|
| `WHATSAPP_TOKEN` | Usuario de sistema del negocio | **Nunca** | Worker (enviar/recibir WhatsApp), `notify._enviar_whatsapp`, derivación de *page tokens* (`token_de_pagina`) |
| `META_TOKEN_KONTROL` | Usuario de sistema, app Kontrol | Nunca | Respaldo, no en producción aún |
| `META_PAGE_ACCESS_TOKEN` | Page token nacido de login humano | Acceso a datos a los 90 días (vencía 02/10/2026) | Fallback de publicación si no hay token de sistema |
| `META_ADS_TOKEN` | Token con `ads_read` | según cómo se generó | Panel de gasto de anuncios (`webapp.py`) |
| `META_APP_SECRET` | Secreto de la app | — | Validar firma de webhooks, `appsecret_proof` |

> [!danger] Trampa del token humano (✅ `config.py:327-331`)
> Un token derivado de un login humano "parece válido" después de los 90 días pero las
> respuestas vuelven **vacías**. Falla como si todo estuviera roto sin motivo. Por eso todo
> se migró al token de **sistema**.

## Cómo generar el token de sistema (🔵)

1. business.facebook.com → **Configuración del negocio → Usuarios → Usuarios del sistema → Agregar**. Nombre p. ej. `eugenia-bot`, rol **Administrador**.
2. **Asignar activos**: la WABA (control total), las páginas (crear contenido / mensajes / control total), las cuentas de Instagram, la cuenta publicitaria, y la **app** (Kontrol).
3. **Generar nuevo token** → elegir la app → caducidad **Nunca** → permisos:
   - `whatsapp_business_messaging` (enviar/recibir)
   - `whatsapp_business_management` (WABA, números, plantillas, suscripciones)
   - `business_management`
   - `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `pages_manage_metadata`, `pages_messaging`
   - `instagram_basic`, `instagram_content_publish`, `instagram_manage_comments`, `instagram_manage_messages`
   - `ads_read` (y `ads_management` si se pausan campañas)
4. Copiar el token **una sola vez** y guardarlo:
   - en la PC → `.env` (`WHATSAPP_TOKEN=…`) desde el panel (Credenciales), que hace backup `.env.bak_<fecha>` y escritura atómica ✅ (`config.write_env`)
   - en Cloudflare → `npx wrangler secret put WHATSAPP_TOKEN` en la carpeta del Worker.
5. Verificar: `GET https://graph.facebook.com/v21.0/debug_token?input_token=<TOKEN>&access_token=<APP_ID>|<APP_SECRET>` → `expires_at: 0`, scopes correctos.

## Rotar un token sin cortar conversaciones

1. Generar el nuevo (p. ej. el de Kontrol ya existe).
2. `wrangler secret put WHATSAPP_TOKEN` (el Worker toma el nuevo en el próximo request, sin redeploy).
3. Guardarlo en el `.env` de la PC desde el panel.
4. Mandar un mensaje de prueba ([[62 - Checklist de pruebas]]).
5. Recién entonces revocar el viejo.
