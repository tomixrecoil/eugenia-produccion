---
tags: [whapi, bitacora]
---

# Bitácora de Whapi

Registro de cada cambio al sistema o a esta documentación. **Toda sesión de Claude que
toque Whapi agrega una línea acá.** Lo más nuevo arriba.

| Fecha | Quién | Qué |
|---|---|---|
| 2026-11-13 | Claude (Claude Code, nube) | Documentados los commits del 08 y 10/11: prompt de ventas de hidroponía reescrito (ventas reales, 3 certezas, moneda local, pago trabado, OXXO, Nicaragua), checkout `J97312812A`, `post_sin_link_temprano` apagada, Charon fuera de los reels, portada automática. Notion actualizado. |
| 2026-11-04 | Claude (Claude Code, nube) | El export de las 12:30 regeneró `eugenia-produccion` y borró el vault y el PR #1. Copia canónica movida a `eugenia-carritos`; vault restaurado en `eugenia-produccion` sobre el `main` nuevo; documentado el rediseño del 02/11 (bóveda cifrada, `state/nichos`, interruptores fb/ig/yt, `publicarDeStock`, `stock/publicados.json`, YouTube desde la nube, `/whisper`, `ctx_precio_pais`, producto bonsái renombrado, fin de XTTS_PUERTOS y del A/B); documento completo subido a Drive en 4 partes. |
| 2026-11-01 | Claude (Claude Code, nube) | Se replicó Whapi "en todos lados": `CLAUDE.md` + skill `.claude/skills/whapi/` en `eugenia-produccion`, `eugenia-carritos` y `sylvana-jarvis`; copia completa del vault en `eugenia-carritos/Whapi/`; memoria + página en Notion (y página «About Tomix» actualizada); carpeta «Whapi» en Google Drive con el resumen, el pipeline y la guía (el vault completo queda en GitHub). Nota nueva [[03 - Contexto para Claude]]. |
| 2026-11-01 | Claude (Claude Code, nube) | Creación del vault (37 notas), Worker de referencia probado, documento consolidado. PR `tomixrecoil/eugenia-produccion#1`. |

## Historia del sistema reconstruida del código (✅)

| Fecha | Hecho |
|---|---|
| 2026-08-18 | 5ª cuenta Gemini/ElevenLabs |
| 2026-08-23 | Se mide el error 131047 (alertas WhatsApp perdidas fuera de 24 h) |
| 2026-08-28 | Eugenia deja de preguntar por el espacio/lugar (creaba objeciones) |
| 2026-08-29 | Token de sistema de la app **Kontrol**; Groq y hottok pasan a `ENV_KEYS`; orden de nichos |
| 2026-08-30 | Se arregla carrera de la cola de IG (releer antes de escribir); subtítulos por nicho |
| 2026-08-31 | Sin tope de reels encolados por día |
| 2026-09-04 | 6ª cuenta Gemini; "+" para sumar cuentas en el panel |
| 2026-09-09 | Pausa manual por nicho, subtítulos creativos, "PENDIENTE" bloquea producción |
| 2026-09-11 | Actividad reciente de Gemini en el panel |
| 2026-09-14 | Toggles `produccion`/`encolado` en R2 |
| 2026-10-02 | Vencía el page token humano (migrado a token de sistema) |
| 2026-10-20 | Bloque de oferta fijo en los copys |
| 2026-10-28 | Producción en GitHub Actions, puerta R2, "Comenta QUIERO", checkout `W99083833C` |
| 2026-11-01 | Palabra por nicho (CULTIVO/BONSAI), horarios desde toggles, mails de aviso apagados, ventas de Hotmart las sube la PC |
| 2026-11-02 | Rediseño: bóveda de credenciales en R2, ajustes de nicho a la nube, interruptores fb/ig/yt, YouTube desde GitHub, reparto parejo de producción, subtítulos estilo viral, fin del A/B |
| 2026-11-08 | Guiones: ganchos genéricos prohibidos en bonsái, formatos con dato; portada automática; landing de los dos nichos → checkout |
| 2026-11-10 | Prompt de ventas de hidroponía nuevo (ventas reales), checkout `J97312812A`, `post_sin_link_temprano` off, Charon fuera, `google-genai<3` |
| 2026-11-04 | Whisper de Cloudflare para subtítulos por palabra; producto de bonsái → «Bonsai en casa desde cero»; regla `ctx_precio_pais`; export regenera `eugenia-produccion` |
