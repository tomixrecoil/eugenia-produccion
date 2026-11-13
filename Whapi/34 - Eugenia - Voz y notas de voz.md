---
tags: [whapi, eugenia, voz]
---

# Eugenia — Voz y notas de voz

## Lo que dice el código (✅)

- `src/pipeline.py:151-153`: *"El XTTS local NO entra acá: es la voz clonada de Sylvana y está para que hable EUGENIA por WhatsApp."*
- `config.py:677-678`: `ELEVEN_SYLVANA_KEY` — *"Voz clonada de Sylvana para las notas de voz (webapp.py)."*
- `config.py:692-693`: `XTTS_PUERTOS` — *"Puertos del servidor XTTS local, en orden de intento (src/local_tts.py)."*

O sea: **la voz de Eugenia es un clon de la voz de Sylvana**, con dos motores:

| Motor | Dónde corre | Uso |
|---|---|---|
| XTTS (Coqui) local | PC, servidor en `XTTS_PUERTOS` | Generar notas de voz gratis |
| ElevenLabs (cuenta `ELEVEN_SYLVANA_KEY`) | Nube | Notas de voz desde el panel (`webapp.py`) |

Ninguna de las dos voces se usa para los reels (eso es Antonio / Charon), para no mezclar marcas.

> [!info] Cambio del 02/11/2026 (✅ export del 04/11)
> `XTTS_PUERTOS` salió de `ENV_KEYS` y las menciones al XTTS local desaparecieron de
> `src/pipeline.py`. `ELEVEN_SYLVANA_KEY` sigue. O sea: hoy las notas de voz con la voz de
> Sylvana salen por ElevenLabs; si el XTTS local sigue en uso ❓ (verificar en `webapp.py`).

## Cómo se manda una nota de voz por la Cloud API (🔵)

1. Generar audio → convertir a **OGG/Opus** mono (para que se vea como nota de voz y no como archivo):
   ```bash
   ffmpeg -i voz.wav -c:a libopus -b:a 32k -ac 1 -ar 48000 voz.ogg
   ```
2. Subir: `POST /{PHONE_ID}/media` (multipart: `file`, `type=audio/ogg`, `messaging_product=whatsapp`) → `{"id": "<MEDIA_ID>"}`.
3. Enviar:
   ```json
   {"messaging_product":"whatsapp","to":"549…","type":"audio","audio":{"id":"<MEDIA_ID>","voice":true}}
   ```

> ❓ Como XTTS corre en la PC y el Worker no puede llamarla, las notas de voz con XTTS
> probablemente se mandan **desde la PC/panel** (a mano o semiautomáticas), no desde el
> Worker en tiempo real. Verificar en `webapp.py` / `src/local_tts.py`.
