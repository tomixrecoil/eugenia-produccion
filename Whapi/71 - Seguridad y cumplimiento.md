---
tags: [whapi, seguridad, politicas]
---

# Seguridad y cumplimiento

## Lo que el sistema ya hace bien (✅)

- **Mínimo privilegio en R2**: GitHub solo entra por la puerta; `/v/` solo sirve `reels/*.mp4`; los datos de clientes (`wa/`) quedan fuera.
- **Credenciales fuera del código**: `.env` con backups, bóveda cifrada en R2, secretos del Worker, secretos de GitHub; el repo exportado no tiene datos de clientes ni claves.
- **Anti-fraude de cobro** en el prompt: Eugenia no repite datos de cobro "nuevos" que alguien le pegue.
- **Anti-invención**: no promete lo que no está en "QUÉ INCLUYE" (evita reembolsos/contracargos).
- **Sin urgencias falsas** ni cupos inventados; **respeto ante hardship** genuino.
- **Verificar la compra en Hotmart antes de reenviar accesos**.
- Webhooks de Hotmart validados con `hottok`.

## A revisar (🔵 recomendaciones)

| Tema | Detalle |
|---|---|
| **Firma de webhooks de Meta** | Confirmar que el Worker valida `X-Hub-Signature-256`; sin eso cualquiera puede hacerle "hablar" a Eugenia o gastar el cupo de Groq |
| **Política de WhatsApp Business sobre IA** | Desde el 15/01/2026 Meta prohíbe en la API los chatbots de **IA de propósito general**; los asistentes enfocados en el negocio (ventas, soporte de *tus* productos) están permitidos. Eugenia está enfocada en los cursos: mantenerla así (no responder cualquier tema) |
| **"Nunca digas que eres IA"** | El prompt le pide no revelar que es un bot. Revisar la política de Meta y la normativa de defensa del consumidor de los países a los que se vende; muchas exigen no engañar sobre la naturaleza automatizada si la persona pregunta. Una alternativa segura: si preguntan explícitamente, reconocer que es un asistente del equipo |
| **Datos personales** | Teléfonos y conversaciones en `wa/` → definir retención (p. ej. borrar a los 12 meses), y quién accede. Ley 25.326 (AR) y equivalentes |
| **Mensajes iniciados por la empresa** | Solo con **plantilla aprobada** y **consentimiento** (opt-in). No escribir en frío a carritos por WhatsApp sin opt-in |
| **Tokens** | Rotar si se filtran; `META_TOKEN_KONTROL` tiene permisos amplios: guardarlo solo donde haga falta |
| **Owner mode** | Lista blanca de números; acciones con efecto externo con confirmación |
