---
tags: [whapi, replicar, guia]
---

# Replicar desde cero (paso a paso)

Tiempo estimado: **1 día** de trabajo + los tiempos de Meta (verificación del negocio: 1–5 días hábiles).

## Fase 0 — Lo que necesitás tener

- [ ] Un número de teléfono con **WhatsApp Business App** (v2.24.17+) en uso, con chip activo.
- [ ] Cuenta de Facebook personal (administradora) y un **portfolio comercial** (business.facebook.com).
- [ ] Documentación del negocio para verificarlo.
- [ ] Cuenta de **Cloudflare** (plan gratuito alcanza; R2 requiere cargar un medio de pago).
- [ ] Cuenta(s) de **Groq** (console.groq.com) → API keys.
- [ ] Node.js 20+ en tu compu (`npx wrangler`).
- [ ] Producto a la venta con link de checkout (Hotmart u otro).

## Fase 1 — Meta: negocio y app

1. business.facebook.com → crear/abrir el portfolio. **Centro de seguridad → Iniciar verificación**.
2. Crear las **páginas** de Facebook de cada producto y vincular sus **Instagram**.
3. developers.facebook.com → **Crear app** tipo Business (ej. "Kontrol"), vinculada al portfolio. → [[11 - Meta - App Kontrol]]
4. Agregar producto **WhatsApp**.
5. Copiar **App ID** y **App Secret** (Configuración → Básica).

## Fase 2 — Conectar el número en coexistencia

6. En la app → WhatsApp → **Inicio rápido / Configuración de la API** → agregar número → **Embedded Signup** → opción **"Conectar la app WhatsApp Business existente"** (si tu app de Meta no muestra esa opción, usar un proveedor/BSP con coexistencia o el *Embedded Signup* con `featureType: "whatsapp_business_app_onboarding"`). → [[13 - Coexistencia]]
7. Escanear el **QR** desde la app WhatsApp Business del celular; elegir compartir historial.
8. Dejar la app del celular abierta y conectada mientras sincroniza (hasta 24 h).
9. Anotar **WABA ID** y **Phone Number ID** (WhatsApp → Configuración de la API).
10. Cargar **método de pago** en la WABA (WhatsApp Manager → Configuración de pagos).

## Fase 3 — Token permanente

11. Portfolio → Usuarios del sistema → crear `eugenia-bot` (Admin) → asignar WABA, páginas, IG, cuenta publicitaria, app.
12. **Generar token**, caducidad *Nunca*, permisos de [[12 - Meta - Tokens y permisos#Cómo generar el token de sistema (🔵)]].
13. Verificar con `debug_token` que `expires_at` sea 0.

## Fase 4 — Cloudflare

14. `npm i -g wrangler` (o usar `npx`) → `npx wrangler login`.
15. Crear el bucket: `npx wrangler r2 bucket create marketing-reels`.
16. Copiar `Whapi/codigo/worker-referencia/` a una carpeta propia. Ajustar `wrangler.toml` (`name`, `bucket_name`).
17. Cargar secretos (`wrangler secret put …`): `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `META_APP_SECRET`, `WA_VERIFY_TOKEN` (inventalo), `GROQ_API_KEY` (+ `_2`, `_3`), `OWNER_NUMBERS` (tu número personal, ej. `549294…`).
18. Subir configuración de Eugenia a R2:
    ```bash
    npx wrangler r2 object put marketing-reels/config/eugenia/venta_bonsai.txt --file prompts/venta_bonsai.txt --content-type "text/plain; charset=utf-8" --remote
    ```
    ```bash
    npx wrangler r2 object put marketing-reels/config/eugenia/bonsai.json --file bonsai.json --content-type application/json --remote
    ```
19. `npm test` (prueba simulada) → `npx wrangler deploy`.

## Fase 5 — Conectar Meta con el Worker

20. App → WhatsApp → **Configuración → Webhook → Editar**: URL `https://<worker>.workers.dev/webhook/whatsapp`, token = `WA_VERIFY_TOKEN` → **Verificar y guardar** (tiene que dar OK: es el GET del paso de verificación).
21. **Administrar campos**: suscribir `messages` y `smb_message_echoes` (y `history`, `smb_app_state_sync` si los vas a usar).
22. Suscribir la app a la WABA:
    ```bash
    curl -X POST "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" -H "Authorization: Bearer <TOKEN>"
    ```
23. Poner la app en modo **Activo (Live)**.

## Fase 6 — Probar

24. Desde otro teléfono escribirle al número → [[62 - Checklist de pruebas]].
25. Mirar en vivo: `npx wrangler tail`.

## Fase 7 — Puertas de entrada (leads)

26. Vincular el WhatsApp a cada página de Facebook (Configuración de la página → Cuentas vinculadas).
27. Anuncios **Click-to-WhatsApp** con saludo de Eugenia y mensaje precargado por nicho → [[41 - Pipeline - Lead desde anuncio Click-to-WhatsApp]].
28. Botón WhatsApp en los reels (`call_to_action` `WHATSAPP_MESSAGE`) → [[45 - Pipeline - Reels con botón de WhatsApp]].
29. `wa.me/<número>` en bios y copys.

## Fase 8 — Lo opcional (como en el sistema original)

- Alertas al dueño → [[44 - Pipeline - Alertas al dueño por WhatsApp]] (crear plantilla de utilidad para no depender de la ventana de 24 h).
- Comentario IG → DM → [[42 - Pipeline - Comentario en Instagram a mensaje privado]].
- Carritos abandonados (repo `eugenia-carritos`) → [[43 - Pipeline - Carritos abandonados]].
- Puerta R2 para GitHub → [[23 - Worker eugenia-puerta-r2]].
- Producción de reels en GitHub Actions → [[46 - Pipeline - Producción y publicación de reels]].
- Panel → [[50 - Frontend - Panel web]].
