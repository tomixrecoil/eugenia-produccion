---
tags: [whapi, pipeline, instagram]
---

# Pipeline — Comentario en Instagram → mensaje privado con el link

## Evidencia (✅ `producir_stock.py:596-610`)

> *"Invitación a comentar (28/10/2026): en Instagram el link del copy no se puede tocar y las
> tiendas de Meta no existen en Argentina. Quien comenta la palabra recibe el link por
> mensaje privado (lo hace el Worker: ver analisis/COMENTARIOS_IG.md)."*

```python
PALABRA_COMENTARIO = {"hidroponia": "CULTIVO", "bonsai": "BONSAI"}
cta = f"💬 Comenta {PALABRA} y te mando el link por privado 📩"
```

La **voz** del reel cierra con la misma palabra ("Comenta CULTIVO y te envío todo al privado.")
✅ (`prompts/voz_comun.txt`, `bonsai_voz_comun.txt`). Hasta el 01/11 decía QUIERO para todos.

## Flujo (🟡 lógica en el Worker; 🔵 APIs)

1. Reel publicado en IG con el copy que termina en "💬 Comenta CULTIVO…".
2. Alguien comenta "cultivo" → webhook de Instagram (`comments`) al Worker.
3. El Worker normaliza (mayúsculas, sin tildes) y verifica la palabra del nicho de esa cuenta.
4. Envía **respuesta privada** al comentario (Private Reply):
   ```
   POST /{IG_USER_ID}/messages   (o /{PAGE_ID}/messages)
   {"recipient":{"comment_id":"<COMMENT_ID>"},"message":{"text":"… https://pay.hotmart.com/…&sck=ig-…"}}
   ```
   Solo se permite **una** respuesta privada por comentario y dentro de 7 días.
5. Opcional: responder públicamente el comentario ("¡Te lo mandé por privado! 📩").
6. Si la persona contesta el DM, sigue la charla en Instagram (no en WhatsApp) ❓, o se la invita al WhatsApp.

Detalle completo en `marketing-agent/analisis/COMENTARIOS_IG.md` (no disponible en GitHub) → [[99 - Pendientes de documentar]].
