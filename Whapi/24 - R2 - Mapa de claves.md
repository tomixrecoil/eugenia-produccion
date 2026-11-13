---
tags: [whapi, cloudflare, r2, datos]
---

# R2 — Mapa de claves del bucket `marketing-reels`

| Clave | Contenido | Escribe | Lee | Certeza |
|---|---|---|---|---|
| `wa/clientes.json` | Clientes/leads de WhatsApp (teléfonos, estado de la charla, nicho, etc.). **Dato sensible**: la ruta `/v/` y la puerta lo bloquean | Worker | Worker, panel | ✅ existencia / ❓ formato |
| `wa/…` (otros) | Probablemente historiales por conversación, pausas, embudo | Worker | Worker, panel | ❓ |
| `queue/<YYYY-MM-DD>.json` | **Lista** de trabajos de Instagram de ese día: `{r2_url, caption, video_key, date, tiktok_id, publish_at, ig_user_id, nicho}` | PC (`publisher.py`) y Worker (stock) | Worker (cron 10 min) | ✅ |
| `reels/<id>.mp4` | Videos listos (los sirve `/v/`) | PC, GitHub (puerta) | Worker → Instagram | ✅ |
| `stock/index.json` | Fila del stock: `[{id, nicho, video_key, r2_url, copy, titulo, creado, voz, guion, tipo, arreglado…}]` | PC, GitHub | Worker (publica; "stock" por WhatsApp) | ✅ |
| `state/toggles.json` | `{nicho: {produccion: bool, encolado: bool, horas: [6,18]}}` | Panel/PC | Worker, PC, GitHub | ✅ |
| `fuentes/usadas.json` | Registro de qué video fuente se usó en cada reel | PC, GitHub | Eugenia (consulta por WhatsApp) | ✅ |
| `stock/publicados.json` | Lo que el Worker ya publicó (id, nicho, `video_key`…) | Worker (`publicarDeStock`) | `subir_youtube_nube.py` | ✅ (04/11) |
| `stock/youtube.json` | `{"desde", "subidos": {id: video_id}}`: lo ya subido a YouTube | GitHub | GitHub | ✅ (04/11) |
| `state/nichos/<nicho>.yaml` | Ajustes del nicho guardados en el panel (voz, mockup, subtítulos…); pisan la copia del export | PC (`config.subir_nicho_nube`) | GitHub (`r2io.bajar_nichos`) | ✅ (04/11) |
| `panel/boveda_produccion.json` | **Bóveda chica cifrada** (AES-GCM, `{"iv","ct"}`) con claves de voz, IA y YouTube para la producción | Panel (`boveda.py`) | GitHub (`r2io.cargar_credenciales` con `BOVEDA_PRODUCCION_KEY`) | ✅ (04/11) |
| `mail/lista.json` | Carritos abandonados a los que escribir | `eugenia-mail-recuperacion` `/ingest` | Ese Worker (cron 8 am) | ✅ (README) |

## Ejemplo de `state/toggles.json` (✅ forma, `toggles.py`)

```json
{
 "hidroponia": {"produccion": true, "encolado": true, "fb": true, "ig": true, "yt": true, "horas": [6, 18]},
 "bonsai":     {"produccion": true, "encolado": true, "fb": true, "ig": true, "yt": true, "horas": [6, 18]}
}
```

Si falta un nicho o una clave → **activo** por defecto (nunca se apaga solo en silencio).
`fb`/`ig`/`yt` existen desde el 02/11/2026: antes vivían escondidos en `niches/*.yaml` (`publish_*`) y el Worker publicaba siempre en FB e IG.

## Ejemplo de un trabajo de la cola de Instagram (✅ `publisher.py:766-771`)

```json
{
 "r2_url": "https://…/reels/7667515649505234198.mp4",
 "caption": "… https://pay.hotmart.com/W99083833C?checkoutMode=10&sck=ig-r-7667515649505234198 …",
 "video_key": "reels/7667515649505234198.mp4",
 "date": "2026-11-02",
 "tiktok_id": "7667515649505234198",
 "publish_at": "2026-11-02T21:00:00Z",
 "ig_user_id": "1784…",
 "nicho": "hidroponia"
}
```

> [!warning] Condición de carrera conocida (✅ `publisher.py:372-381`)
> El Worker (cron cada 10 min) y la PC escriben el **mismo** `queue/<fecha>.json`. Por eso
> la PC **relee** el archivo justo antes de escribir. Para un diseño nuevo conviene una clave
> por trabajo (`queue/<fecha>/<id>.json`) o Durable Objects.

## Formato sugerido para conversaciones (🔵 para replicar)

```json
// wa/conv/5215512345678.json
{
 "wa_id": "5215512345678",
 "nicho": "bonsai",
 "origen": {"tipo": "ad", "ad_id": "…", "ctwa_clid": "…"},
 "creado": "2026-11-01T14:03:00Z",
 "ultimo_entrante": "2026-11-01T14:05:10Z",
 "pausado_hasta": null,
 "link_enviado": true,
 "angulos_usados": ["garantia"],
 "historial": [
   {"rol": "cliente", "t": "…", "texto": "Hola, quiero aprender…", "wamid": "…"},
   {"rol": "eugenia", "t": "…", "texto": "¡Qué bueno…", "wamid": "…"},
   {"rol": "humano",  "t": "…", "texto": "(eco desde el celular)", "wamid": "…"}
 ]
}
```
