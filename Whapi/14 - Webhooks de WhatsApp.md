---
tags: [whapi, meta, webhooks, referencia]
---

# Webhooks de WhatsApp (payloads de referencia)

Todo lo de esta nota es 🔵 **estándar de la Cloud API** (formato oficial). Es lo que recibe
el Worker de Eugenia.

## 1. Verificación (una sola vez, al configurar la URL)

Meta hace:

```
GET https://<worker>/<ruta>?hub.mode=subscribe&hub.verify_token=<TU_TOKEN>&hub.challenge=1158201444
```

El Worker responde **200** con el cuerpo exactamente igual a `hub.challenge` **solo si**
`hub.verify_token` coincide con su secreto. Si no, 403.

## 2. Mensaje entrante de texto

```http
POST /<ruta> HTTP/1.1
Content-Type: application/json
X-Hub-Signature-256: sha256=<HMAC-SHA256(cuerpo crudo, APP_SECRET)>
```

```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "<WABA_ID>",
    "changes": [{
      "field": "messages",
      "value": {
        "messaging_product": "whatsapp",
        "metadata": { "display_phone_number": "5492944508833", "phone_number_id": "<PHONE_ID>" },
        "contacts": [{ "profile": { "name": "María" }, "wa_id": "5215512345678" }],
        "messages": [{
          "from": "5215512345678",
          "id": "wamid.HBgN...",
          "timestamp": "1730490000",
          "type": "text",
          "text": { "body": "Hola, quiero aprender las técnicas del Bonsái" }
        }]
      }
    }]
  }]
}
```

> [!warning] El nombre del perfil NO es el nombre de la persona
> `contacts[0].profile.name` es lo que la persona puso en su WhatsApp (puede ser un apodo,
> un emoji o el nombre de otro). El prompt prohíbe usar nombres que la persona no dio ella
> misma ✅ (`venta_*.txt`: "NUNCA inventes el nombre de la persona").

## 3. Mensaje que viene de un anuncio Click-to-WhatsApp

Igual que el anterior, pero el mensaje trae `referral`:

```json
"messages": [{
  "from": "5215512345678", "id": "wamid...", "type": "text",
  "text": { "body": "Hola, quiero aprender las técnicas del Bonsái" },
  "referral": {
    "source_url": "https://fb.me/xxxx",
    "source_type": "ad",
    "source_id": "<AD_ID>",
    "headline": "El Arte del Bonsái",
    "body": "¡Hola! Soy Eugenia, de Bonsái en Casa...",
    "ctwa_clid": "<click id>"
  }
}]
```

`source_id` (ID del anuncio) + `ctwa_clid` permiten saber de qué anuncio vino el lead y
de qué **nicho** es. Ver [[41 - Pipeline - Lead desde anuncio Click-to-WhatsApp]].

## 4. Otros tipos de mensaje entrante

| `type` | Campo | Qué hace Eugenia |
|---|---|---|
| `image` | `image.id`, `caption` | Si es un **comprobante** de Western Union/transferencia: agradecer, avisar que se verifica (el prompt prohíbe decir "no puedo ver imágenes") ✅ |
| `audio` | `audio.id` (ogg/opus) | 🔵 Bajar con `GET /{media-id}` → URL → descargar con el token; transcribir (Whisper de Groq) o responder pidiendo texto ❓ |
| `button` / `interactive` | `button.text` / `interactive.button_reply` | Respuestas a plantillas o botones |
| `reaction`, `sticker`, `location`, `contacts`, `document`, `video` | | Ignorar o respuesta corta |
| `unsupported` | | Ignorar |

## 5. Estados de mensajes enviados

```json
"statuses": [{
  "id": "wamid...", "status": "failed", "timestamp": "...", "recipient_id": "549...",
  "errors": [{ "code": 131047, "title": "Re-engagement message",
               "message": "More than 24 hours have passed since the recipient last replied" }]
}]
```

`status` ∈ `sent` → `delivered` → `read`, o `failed`. ✅ El código ya documenta el caso
**131047**: el `POST /messages` devuelve 200, pero el fallo llega **después**, por este
webhook (`notify.py:232-237`).

## 6. Eco de coexistencia (Tomix contestó desde el celular)

```json
{ "field": "smb_message_echoes",
  "value": {
    "messaging_product": "whatsapp",
    "metadata": { "display_phone_number": "5492944508833", "phone_number_id": "<PHONE_ID>" },
    "message_echoes": [{
      "from": "5492944508833", "to": "5215512345678",
      "id": "wamid...", "timestamp": "...", "type": "text",
      "text": { "body": "Hola! te escribo yo, Tomi" }
    }]
  } }
```

## 7. Reglas de oro del receptor

1. **Responder 200 rápido** (Meta reintenta con *backoff* si no recibe 200 en ~unos segundos, y hasta por días). En Workers: validar, `ctx.waitUntil(procesar())` y devolver 200.
2. **Validar la firma** `X-Hub-Signature-256` con el `APP_SECRET` sobre el cuerpo **crudo**.
3. **Deduplicar por `wamid`** (los reintentos llegan repetidos).
4. Un mismo POST puede traer **varios** `entry` / `changes` / `messages`.
5. Ignorar `statuses` para responder (solo registrar) y nunca responder a ecos.
