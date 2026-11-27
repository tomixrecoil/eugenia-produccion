---
tags: [whapi, pendientes]
---

# Pendientes de documentar

Lo que **no se pudo verificar** porque el código vive solo en la PC Windows "MYX"
(`marketing-agent`), que no es accesible desde una sesión en la nube.

## Para cerrar los huecos

Cualquiera de estas opciones alcanza:

1. **Subir `marketing-agent` a GitHub** como repo **privado** (excluyendo `.env*`, `state/`, `PANEL_KEY.txt`, `youtube_token*.json`, datos de clientes) y darle acceso a Claude.
2. O, como mínimo, subir la carpeta `marketing-agent/cloudflare-worker/` (sin `.dev.vars`) y `webapp.py`.
3. O abrir una sesión de Claude Code **local** en la PC dentro de `marketing-agent` y pedir "completá el vault Whapi con el código real".

## Lista de preguntas abiertas (❓)

- [ ] Ruta exacta del webhook de WhatsApp en el Worker y si **valida la firma** `X-Hub-Signature-256`.
- [ ] ¿La URL de callback está configurada en la app **Kontrol** o en otra app?
- [ ] Campos suscritos (¿`smb_message_echoes`?) y qué hace el Worker con los ecos (¿pausa a Eugenia?).
- [ ] Estructura de `wa/clientes.json` y demás claves `wa/…`.
- [ ] Cómo detecta el nicho de una charla y al **dueño**.
- [ ] Orden exacto de la cascada Groq (cuentas vs. modelos) y si hay fallback a Gemini.
- [ ] Implementación de cada regla `post_*` y del bloque `[SITUACIÓN]`.
- [ ] De dónde sale `{{PRECIO}}` (¿`sync_precios.py` → R2?) y `{{DATOS_COBRO}}`.
- [ ] ¿Manda "leído" / "escribiendo…"? ¿Qué pausa usa antes del link?
- [ ] ¿Transcribe audios / lee comprobantes?
- [ ] Seguimientos automáticos (¿el `sck` `wa-segui` es un seguimiento programado?).
- [ ] `analisis/COMENTARIOS_IG.md` (flujo comentario → DM).
- [ ] Endpoints del panel en el Worker (`PANEL_KEY`) y del webhook de Hotmart.
- [ ] Notas de voz: ¿desde el Worker o desde el panel? (XTTS corre en la PC).

- [ ] `analisis/REDISENO_0211.md`, `analisis/AJUSTES_DECORACION.md` y `boveda.py` (rediseño del 02/11: bóveda, interruptores fb/ig/yt).
- [ ] Qué hace exactamente `ctx_precio_pais` y de dónde saca los precios por país.
- [ ] ¿Sigue en uso el XTTS local para las notas de voz?
- [ ] Que `exportar_produccion.py` conserve `Whapi/`, `CLAUDE.md` y `.claude/` (hoy los borra).

- [ ] Quién arma el bloque `[PRECIO — REGLA ABSOLUTA]` (precio en moneda local) para hidroponía y si reemplaza a `ctx_precio_pais`.
- [ ] ¿Hay `hidroponia_incluye_ar.txt` con contenido? (en el export está vacío: `{{QUE_INCLUYE}}` de hidroponía podría salir vacío).

Cuando se resuelvan, actualizar las notas marcadas con 🟡/❓ y cambiarlas a ✅.
