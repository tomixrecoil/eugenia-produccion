---
tags: [whapi, cloudflare, worker, hotmart]
---

# Worker `eugenia-mail-recuperacion`

URL: `https://eugenia-mail-recuperacion.goldentimeshift.workers.dev` ✅ (README de `eugenia-carritos`)

## Qué hace

Le manda un **mail de recuperación** a cada persona que dejó un **carrito abandonado** en
Hotmart, con la PC apagada.

| Endpoint / disparador | Qué hace | Certeza |
|---|---|---|
| `POST /ingest?key=<MAIL_KEY>` | Recibe la lista JSON `[{email, nombre, ts}]` y la guarda en R2 en `mail/lista.json` | ✅ |
| Cron **8:00 ART** (11:00 UTC) | Recorre la lista y le escribe a cada uno "al día siguiente del abandono" | ✅ |

## Por qué existe separado (✅)

El Worker **no puede** consultar Hotmart: el token viene URL-encodeado (`%2B`, `%3D`) y se
corrompe entre Cloudflare y Hotmart (HTTP 400). Desde una IP normal (runner de GitHub)
funciona. Entonces el descubrimiento se hace en GitHub Actions → [[43 - Pipeline - Carritos abandonados]].

## Autenticación

`MAIL_KEY` en la query (`?key=`). ✅ (`descubrir_carritos.py:94`)
