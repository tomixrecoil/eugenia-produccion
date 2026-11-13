# Instrucciones permanentes para Claude

## Whapi: el proyecto más importante de Tomix

**Whapi** es el WhatsApp automatizado del negocio (+54 9 294 450-8833) atendido por
**Eugenia** (WhatsApp Cloud API en coexistencia, app de Meta «Kontrol», Workers de
Cloudflare, R2, Groq). La copia **canónica** del vault de Obsidian está en
`tomixrecoil/eugenia-carritos` → `Whapi/`. La carpeta `Whapi/` de este repo es una copia.

> ⚠️ Este repo es un export de `marketing-agent` (`exportar_produccion.py`). El export del
> 04/11/2026 lo regeneró con historia nueva y borró `Whapi/`, este archivo y `.claude/`.
> Si faltan, se vuelven a copiar desde `eugenia-carritos`. El arreglo de fondo es que
> `exportar_produccion.py` conserve esas tres rutas.

Siempre, en cualquier sesión:

1. Antes de tocar algo relacionado con WhatsApp, Eugenia, Meta, Cloudflare, R2, Hotmart o
   los reels, leé `Whapi/03 - Contexto para Claude.md` y después `Whapi/00 - Inicio.md`.
2. Todo cambio al sistema se documenta en el vault **canónico** (`eugenia-carritos`) en el
   mismo trabajo, se anota en `Whapi/98 - Bitácora.md` y se copia acá. Mantené la leyenda
   ✅ verificado / 🟡 deducido / 🔵 estándar / ❓ sin confirmar.
3. Nunca escribas valores de secretos (tokens, claves, CBU) en el vault ni en commits: solo nombres.

La skill `.claude/skills/whapi/` resume lo mismo para cargarse sola.
