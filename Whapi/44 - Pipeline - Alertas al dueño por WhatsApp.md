---
tags: [whapi, pipeline, alertas]
---

# Pipeline — Alertas al dueño por WhatsApp (todo ✅ `src/notify.py`)

El sistema le avisa a Tomix por WhatsApp **desde el número del negocio** hacia su número
personal (`ALERT_WHATSAPP`).

## Tres funciones

| Función | Cuándo | Canales |
|---|---|---|
| `alert(asunto, cuerpo, dedup_key)` | Anomalías (cuotas agotadas, sin voz, fallos) | Mail → si falla, WhatsApp. Anti-repetición 12 h en `state/avisos.json`. **Mails apagados por default desde 01/11** (`AVISOS_MAIL=1` para prender) → hoy retorna sin mandar |
| `whatsapp(asunto, cuerpo)` | Eventos de rutina: **cada reel publicado/programado** (`publisher._avisar_reel`) | WhatsApp **y** mail (si están prendidos) |
| `_enviar_whatsapp` | Interna | `POST /{WHATSAPP_PHONE_ID}/messages` |

## El envío exacto

```python
requests.post(f"https://graph.facebook.com/{ver}/{phone_id}/messages",
    headers={"Authorization": f"Bearer {token}"},
    json={"messaging_product": "whatsapp", "to": destino, "type": "text",
          "text": {"preview_url": False, "body": f"{emoji} *{asunto}*\n\n{cuerpo}"[:3900]}},
    timeout=30)
```

- Emoji del asunto según el tema (💲 precio, 💰 venta, 🔇 voz, 🧠 Gemini, 🩺 salud, 🎬 reel, 💬 WhatsApp, ⏰, 🚨; default 📣).
- Cuerpo recortado a 3.900 caracteres (límite de WhatsApp: 4.096).

## La trampa de las 24 h (medido el 23/08)

Si Tomix **no** le escribió al número del negocio en las últimas 24 h, Meta acepta el POST
(**200**) y después lo descarta con el error **131047 "Re-engagement message"**, que llega
**por webhook**, no en la respuesta. Por eso:

- se manda también por mail (cuando está prendido),
- 🔵 alternativa robusta: usar una **plantilla de utilidad** aprobada (p. ej. `alerta_sistema` con `{{1}}` asunto y `{{2}}` cuerpo), que sí se puede mandar fuera de la ventana,
- 🔵 truco operativo: que Tomix le mande cualquier cosa al número una vez por día.

## Ejemplo de aviso de reel

```
🎬 *Reel programado (bonsai): 7478146540746427703*

Nicho: bonsai
Video: 7478146540746427703
Cuándo: 02/11/2026 18:00

📘 Facebook: 1234567890
📸 Instagram: encolado (https://…/reels/7478….mp4)
▶️ YouTube: https://youtube.com/shorts/abc123

--- COPY ---
…
```
