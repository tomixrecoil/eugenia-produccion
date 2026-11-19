---
tags: [whapi, troubleshooting]
---

# Errores conocidos y troubleshooting

## Ya ocurrieron en este sistema (✅, con fecha cuando el código la da)

| Síntoma | Causa | Arreglo |
|---|---|---|
| El vault `Whapi/`, `CLAUDE.md` y el PR desaparecieron de `eugenia-produccion` (04/11/2026) | `exportar_produccion.py` regeneró el repo con historia nueva | Copia canónica movida a `eugenia-carritos`; volver a copiar a `eugenia-produccion` después de cada export (o que el export conserve esas carpetas) |
| Alertas por WhatsApp "enviadas" (200) que nunca llegan (23/08) | Error **131047**: el dueño no escribió al número en 24 h; el fallo llega async por webhook | Mandar también por mail / usar plantilla / escribir al número 1 vez por día |
| Hidroponía deja de publicar en FB/IG sin aviso | Conectar la página de bonsái pisaba el `META_PAGE_ACCESS_TOKEN` global | `token_de_pagina()` deriva el token de cada página del token de sistema |
| Token "válido" pero respuestas vacías | Page token humano: acceso a datos vence a los 90 días (02/10/2026) | Token de sistema |
| Scripts reciben 401 del Worker | `PANEL_KEY` no estaba en `ENV_KEYS` → clave vacía | Agregada |
| Groq/hottok "invisibles" para la PC | Solo estaban como secretos de Cloudflare | Sumados a `ENV_KEYS` (29/08) |
| Leads de hidroponía escuchaban 60 % de descuento | 60 clavado en el prompt del Worker | Campo `descuento` por nicho |
| Link partido en "…&sck=wa" + "\|euge" | La barra `\|` no es válida en URL; WhatsApp corta el autolink | Separador `-` en `sck()` |
| Carritos: HTTP 400 desde Cloudflare | Token de Hotmart URL-encodeado se corrompe | Consulta desde GitHub → `/ingest` |
| 403 / error 1010 en la puerta R2 | Cloudflare bloquea `Python-urllib` | `user-agent` propio |
| Publicación de IG de una hora "desaparece" | Carrera PC ↔ cron del Worker sobre `queue/<fecha>.json` | Releer antes de escribir |
| "Guardar credenciales" borraba claves | `write_env` reescribía desde plantilla de 18 líneas | Edición en el lugar + backup |
| Lead creó la objeción "no tengo lugar" | Eugenia preguntó dónde pondría el sistema (28/08) | Prohibido preguntar por el espacio |
| Reclamo de publicidad engañosa | Se ofrecían módulos "gratis/sin costo" | Prohibido decir "gratis/regalo" |
| Un interesado bloqueó | Urgencia falsa ("el precio sube") | Precio fijo, prohibida toda urgencia |

## Diagnóstico rápido (🔵)

| Pasa esto | Mirá |
|---|---|
| Eugenia no contesta nada | `wrangler tail`; ¿llega el POST? → si no: `subscribed_apps`, campos del webhook, app en *Live*; si llega con 401: `META_APP_SECRET` |
| Contesta dos veces | Falta dedupe por `wamid` o se tarda en devolver 200 |
| `(#131030) Recipient phone number not in allowed list` | App en modo desarrollo / número de prueba |
| `(#190) token expired` / `OAuthException` | Token vencido o revocado → [[12 - Meta - Tokens y permisos]] |
| `131047` | Fuera de la ventana de 24 h → plantilla |
| `131026` | El destinatario no puede recibir (no tiene WhatsApp / versión vieja) |
| `130429` / `131056` | Límite de velocidad (20 mps en coexistencia / mismo par emisor-receptor) |
| Groq 429 en todas | Cupo agotado → `/wa-groq?listar=1`; sumar cuenta o modelo |
| Se dejó de ver en el celular | Coexistencia caída: abrir la app WhatsApp Business (al menos cada 14 días) |
