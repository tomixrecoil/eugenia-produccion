---
tags: [whapi, cloudflare, worker, seguridad]
---

# Worker `eugenia-puerta-r2` — la "puerta" de R2

## Por qué existe (✅ `r2io.py:3-12`, README de `eugenia-produccion`)

GitHub Actions no tiene el login de wrangler de Tomix. Darle una llave de API de R2 del
**bucket entero** le permitiría ver **las conversaciones y los teléfonos de los clientes**
(`wa/…`), que viven en el mismo bucket. Entonces se creó un Worker intermedio con:

- una **clave propia** (`PUERTA_R2_KEY`, en cabecera `x-clave`),
- que **solo** deja tocar los videos, el stock y los registros de fuentes.

## Interfaz (✅ `r2io.py`)

```
GET    {PUERTA_R2_URL}/o/<key>   -> bytes del objeto (404 si no existe)
PUT    {PUERTA_R2_URL}/o/<key>   -> sube (content-type + content-length)
DELETE {PUERTA_R2_URL}/o/<key>
Cabeceras: x-clave: <PUERTA_R2_KEY>
           user-agent: eugenia-produccion/1.0   (sin esto Cloudflare devuelve 403 / error 1010)
```

Las claves se pasan **sin** el prefijo `marketing-reels/` (la puerta trabaja dentro del bucket).

## Ruta `/whisper` (✅ desde el 04/11/2026, `src/voz_charon.py`)

```
POST {PUERTA_R2_URL}/whisper     cuerpo: MP3 de la voz     cabecera: x-clave
-> palabras con inicio y fin (Whisper de Cloudflare Workers AI, plan gratis)
```

La producción la usa para sincronizar los subtítulos palabra por palabra con la voz
Charon. Si falla, vuelve a cortar por pausas. 🔵 En el Worker: binding `[ai]` y
`env.AI.run("@cf/openai/whisper", {audio: [...bytes]})`.

## Prefijos permitidos (🟡, por lo que usa la nube)

`reels/`, `reels_stock/`, `stock/` (incluye `publicados.json` y `youtube.json`), `fuentes/`,
`state/toggles.json`, `state/nichos/`, `panel/boveda_produccion.json` (cifrada). **Nunca** `wa/`, `mail/`.

## Implementación mínima de referencia (🔵)

```js
const PERMITIDOS = [/^reels\/[\w.-]+\.mp4$/, /^reels_stock\//, /^stock\//, /^fuentes\//, /^state\/toggles\.json$/];
export default {
  async fetch(req, env) {
    if (req.headers.get("x-clave") !== env.PUERTA_R2_KEY) return new Response("no", { status: 401 });
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/o/")) return new Response("ruta", { status: 404 });
    const key = decodeURIComponent(url.pathname.slice(3));
    if (key.includes("..") || !PERMITIDOS.some(r => r.test(key))) return new Response("prohibido", { status: 403 });
    if (req.method === "GET") {
      const o = await env.R2.get(key);
      return o ? new Response(o.body, { headers: { "content-type": o.httpMetadata?.contentType || "application/octet-stream" } })
               : new Response("no existe", { status: 404 });
    }
    if (req.method === "PUT") {
      await env.R2.put(key, req.body, { httpMetadata: { contentType: req.headers.get("content-type") || "" } });
      return new Response("ok");
    }
    if (req.method === "DELETE") { await env.R2.delete(key); return new Response("ok"); }
    return new Response("método", { status: 405 });
  }
};
```
