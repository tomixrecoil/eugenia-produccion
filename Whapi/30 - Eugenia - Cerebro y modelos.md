---
tags: [whapi, eugenia, ia]
---

# Eugenia — Cerebro y modelos

## Quién es Eugenia

Asesora de ventas **ficticia** con nombre humano que atiende el WhatsApp de los dos
negocios. Se presenta como "Eugenia es mi nombre" / "Euge es mi nombre" (nunca "soy
Eugenia"). ✅ (`venta_*.txt`). Además aparece en:

- los **anuncios** ("¡Hola! Soy Eugenia, de Bonsái en Casa…") ✅,
- la **voz** de notas de voz (XTTS local con la voz clonada de Sylvana) ✅ → [[34 - Eugenia - Voz y notas de voz]],
- el **modo dueño**, donde Tomix le pide cosas por WhatsApp ✅ → [[33 - Eugenia - Modo dueño]].

## Modelo de lenguaje: Groq (✅ `parametros_ia.json`, `config.py:636-639`)

```json
"groq": {
  "modelos": ["openai/gpt-oss-20b", "qwen/qwen3.6-27b", "groq/compound-mini"],
  "temperatura": 0.7,
  "max_tokens": 700
}
```

- **3 cuentas** (`GROQ_API_KEY`, `_2`, `_3`) "para sumar cupo: el gratis se agota rápido con varias charlas de leads en simultáneo". ✅
- **3 modelos en cascada** 🟡: se prueba el primero; si falla / no hay cupo (HTTP 429), el siguiente.
- Diagnóstico: `GET /wa-groq?listar=1` en el Worker ✅.
- API (🔵): `POST https://api.groq.com/openai/v1/chat/completions` — compatible con OpenAI.

```mermaid
flowchart TD
  A[Prompt listo] --> B{cuenta 1\nmodelo 1}
  B -- 200 --> OK[respuesta]
  B -- 429/5xx --> C{cuenta 2\nmodelo 1}
  C -- falla --> D{cuenta 3\nmodelo 1}
  D -- falla --> E{modelo 2\n(qwen3.6-27b)}
  E -- falla --> F{modelo 3\n(compound-mini)}
  F -- falla --> G[sin respuesta:\nno se manda nada\n+ alerta ❓]
```

> El orden exacto (rotar cuentas antes que modelos, o al revés) ❓ no está en los repos.

## Gemini (✅)

`temperatura 0.85` en `parametros_ia.json`. Se usa para **reels** (análisis de video, guiones,
copys), con 6 cuentas rotativas. No hay evidencia de que conteste WhatsApp.

## Qué recibe el modelo en cada turno (🟡 por los placeholders del prompt)

1. **System**: `prompts/venta_<nicho>.txt` con `{{PRECIO}}`, `{{QUE_INCLUYE}}`, `{{DATOS_COBRO}}` reemplazados → [[31 - Eugenia - Prompt de venta]].
2. **Contexto**: la **hora local** del cliente para el saludo ("Buen día / Buenas tardes / Buenas noches"), el país si se conoce (Venezuela → Western Union; Argentina → transferencia).
3. **Bloque `[SITUACIÓN]`**: instrucción dinámica según el momento (objeción de precio → mencionar el descuento; ya se mandó link; etc.).
4. **Catálogo** de otros cursos con sus enlaces (el prompt advierte "si más abajo aparece un catálogo…").
5. **Historial** de la charla (el prompt dice "Mira el historial: no repitas lo ya dicho").
6. **Último mensaje** del cliente.

Salida: **solo el texto a enviar** ("Escribe SOLO el mensaje a enviar, sin comillas ni explicaciones").
Después pasa por las [[32 - Eugenia - Reglas post-proceso]].
