---
tags: [whapi, eugenia, reglas]
---

# Eugenia — Reglas post-proceso

El LLM no siempre obedece el prompt. Por eso, **después** de que Groq responde y **antes**
de mandar, el Worker pasa el texto por reglas de código que se prenden/apagan por nicho
desde el panel (pestaña **Reglas**).

✅ Archivos: `prompts/hidroponia_reglas.json`, `prompts/bonsai_reglas.json`
(formato `{"regla": {"activa": bool, "texto": ""}}`; `texto` permite personalizar el mensaje que usa la regla).

## Estado al 01/11/2026

| Regla | Hidroponía | Bonsái | Qué hace (🟡 deducido del nombre + el prompt) |
|---|:-:|:-:|---|
| `post_formato_final` | ✅ on | ✅ on | Limpia formato: saca `**negritas**`/asteriscos, convierte `[texto](url)` en URL pelada, recorta a ~500 caracteres, quita comillas envolventes |
| `post_separar_cta_transfer` | ✅ on | ✅ on | Separa el llamado a la acción del bloque de transferencia/cobro en mensajes/renglones distintos |
| `post_pausa_link` | ✅ on | ✅ on | Manda el link **aparte**, con una pausa breve, para que la tarjeta de preview se vea sola |
| `post_sacar_link_1` | ✅ on | — | Saca el link del **primer** mensaje de la charla (no se manda link en el saludo) |
| `post_sin_link_temprano` | ✅ on | — | Saca el link si todavía no hubo señal de interés |
| `post_link_si_lo_pide` | ✅ on | — | Si el cliente pidió el link/precio y el modelo no lo puso, lo agrega |
| `post_forzar_saludo` | ✅ on | — | Asegura el saludo por hora local en el primer mensaje |
| `post_completar_bloque_transfer` | ✅ on | — | Si menciona transferencia (AR) completa el bloque con alias/CBU/banco/monto (solo si están **los cuatro**) |
| `post_forzar_precio` | ✅ on | — | Fuerza el precio **exacto** `{{PRECIO}}` si el modelo puso otro número/redondeó |
| `ctx_precio_pais` (desde 04/11) | — | ✅ on | Regla de **contexto** (prefijo `ctx_`, actúa antes del LLM, no después): le pasa a Eugenia el precio según el país del cliente ❓ detalle |
| `post_asegurar_link_cierre` | ⛔ off | — | Agregaría el link en toda pregunta de cierre |
| `post_un_solo_link` | ⛔ off | — | Dejaría un único link por mensaje |

> Una regla que no figura en el JSON de un nicho, el Worker la toma con su default ❓.

## Orden sugerido para replicar (🔵)

```
texto_llm
 → quitar comillas/explicaciones
 → post_formato_final        (markdown → texto plano, link pelado)
 → post_forzar_precio
 → post_sacar_link_1 / post_sin_link_temprano / post_link_si_lo_pide
 → post_un_solo_link
 → post_completar_bloque_transfer
 → post_separar_cta_transfer
 → post_pausa_link           (divide en 2 envíos: texto, [pausa], link)
 → enviar
```
