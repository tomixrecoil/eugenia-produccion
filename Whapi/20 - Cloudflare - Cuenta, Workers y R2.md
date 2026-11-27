---
tags: [whapi, cloudflare]
---

# Cloudflare — Cuenta, Workers y R2

## La cuenta

- Subdominio de Workers: **`goldentimeshift.workers.dev`** ✅ (`armar_stock.py:47`, README de carritos).
- Login en la PC con `npx wrangler login` (el login de Tomix). ✅ (`r2io.py:5`: "En la PC todo va por `npx wrangler` con el login de Tomix").
- El código del Worker principal vive en `marketing-agent/cloudflare-worker/` en la PC ✅ (`toggles.py:22`: `WORKER = ROOT / "cloudflare-worker"`; todos los `wrangler` se corren con `cwd=cloudflare-worker`).

## Los tres Workers

| Worker | URL | Rol | Nota |
|---|---|---|---|
| `marketing-ig-scheduler` | `https://marketing-ig-scheduler.goldentimeshift.workers.dev` | **Eugenia**: webhooks de WhatsApp/IG/Hotmart, cron de publicación cada 10 min, ruta pública `/v/` de videos, endpoints del panel | [[21 - Worker marketing-ig-scheduler (Eugenia)]] |
| `eugenia-mail-recuperacion` | `https://eugenia-mail-recuperacion.goldentimeshift.workers.dev` | Mails a carritos abandonados (`/ingest` + cron 8 am ART) | [[22 - Worker eugenia-mail-recuperacion]] |
| `eugenia-puerta-r2` | `PUERTA_R2_URL` (variable de GitHub) | Proxy de R2 con clave propia y alcance limitado para GitHub Actions | [[23 - Worker eugenia-puerta-r2]] |

> El nombre `marketing-ig-scheduler` es histórico: nació como programador de Instagram y
> fue creciendo hasta ser el backend de Eugenia. 🟡

## R2

- Bucket: **`marketing-reels`** ✅ (`r2io.py:24`, `armar_stock.py:45`).
- Binding en el Worker (🔵, nombre exacto ❓): algo como `[[r2_buckets]] binding = "R2"` en `wrangler.toml`.
- Acceso:
  - Worker → binding directo (`env.R2.get/put`).
  - PC → `npx wrangler r2 object get|put|delete marketing-reels/<key> --remote` ✅.
  - GitHub Actions → **solo** vía `eugenia-puerta-r2` ✅.
- Mapa completo de claves → [[24 - R2 - Mapa de claves]].

## Por qué Cloudflare (🟡 de los comentarios)

- Corre **24/7 sin la PC** (el objetivo explícito de casi todo el diseño).
- **Cron Triggers** nativos (cada 10 min para publicar; 8 am para mails).
- R2 sin costo de salida: sirve los MP4 que Instagram necesita descargar por URL pública.
- **No tiene ffmpeg** → por eso los videos se producen en la PC o en GitHub Actions y el Worker solo publica ✅ (`armar_stock.py:7-10`).

## Limitaciones encontradas en la práctica (✅)

| Problema | Solución adoptada |
|---|---|
| El token de Hotmart viene URL-encodeado (`%2B`, `%3D`) y se **corrompe** en el camino Cloudflare↔Hotmart (HTTP 400) | Consultar Hotmart desde GitHub Actions y empujar a `/ingest` (repo `eugenia-carritos`) |
| Cloudflare bloquea el user-agent `Python-urllib` (error 1010 → 403) | Mandar `user-agent: eugenia-produccion/1.0` (`r2io.py:43-44`) |
| Hotmart responde 403 a GitHub (01/11/2026) | Las ventas para el panel las sube la PC (commit `a222552`) |

## Comandos de wrangler que usa el sistema (✅)

```bash
npx wrangler r2 object get marketing-reels/state/toggles.json --remote --pipe
```
```bash
npx wrangler r2 object put marketing-reels/stock/index.json --file index.json --content-type application/json --remote
```
```bash
npx wrangler r2 object delete marketing-reels/reels/<id>.mp4 --remote
```

Y los de despliegue (🔵):

```bash
npx wrangler deploy
```
```bash
npx wrangler secret put WHATSAPP_TOKEN
```
```bash
npx wrangler tail marketing-ig-scheduler
```
