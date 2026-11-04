---
tags: [whapi, pipeline, facebook]
---

# Pipeline — Reels con botón de WhatsApp (todo ✅)

## El botón

`src/publish.py:23-27`:

```python
WHATSAPP_CTA = json.dumps({"type": "WHATSAPP_MESSAGE",
                           "value": {"app_destination": "WHATSAPP"}})
```

- Es el **default** de `publish_reel()`, y además `publisher.publicar_reel` lo pasa **explícito** ("Requisito del dueño: TODOS los reels de FB tienen que tener el botón").
- Se manda en la fase **finish** de la subida resumable de reels (`/{page_id}/video_reels`, fases `start` → `upload` a `rupload.facebook.com` → `finish`).
- La API lo acepta pero **no permite releerlo**: solo se verifica mirando el reel en Facebook.
- El botón abre WhatsApp con el número vinculado a la **página** (hay que tener el WhatsApp vinculado en la configuración de la página: Configuración → Cuentas vinculadas → WhatsApp → +5492944508833). 🔵

## El link en el texto

Copys de reels: `📲 Escríbeme por WhatsApp 👉 https://wa.me/5492944508833` en los prompts de copy
(`gpt_copy.txt`, `hidroponia_gpt.txt`, `bonsai_gpt.txt`) y el link de compra etiquetado por
plataforma y video (`sck=fb-r-<id>`, `ig-r-<id>`) en `publisher.con_origen()`.

## Resultado

Cada reel es una puerta de entrada al WhatsApp → el mensaje sigue el
[[40 - Pipeline segundo a segundo - mensaje entrante]].
