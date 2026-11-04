---
tags: [whapi, moc]
aliases: [Whapi, Índice]
actualizado: 2026-11-01
---

# Whapi — WhatsApp automatizado de Eugenia

> Documentación completa de cómo funciona el WhatsApp **+54 9 294 450-8833** del negocio
> (Ecosistema Hidropónico / Bonsái en Casa), atendido automáticamente por **Eugenia**:
> desde la app de Meta Developers **Kontrol**, pasando por la **WhatsApp Cloud API en
> coexistencia** con la app WhatsApp Business, los **Workers de Cloudflare** y **R2**,
> hasta el panel web y la PC.

Si es la primera vez que entrás, leé en este orden:

0. [[03 - Contexto para Claude]] — **resumen condensado de todo Whapi** (lo que cualquier Claude lee primero).
1. [[01 - Mapa general]] — el dibujo completo en una página.
2. [[02 - Fuentes y nivel de certeza]] — **qué está verificado en código y qué no** (leer sí o sí).
3. [[40 - Pipeline segundo a segundo - mensaje entrante]] — el corazón: qué pasa desde que alguien escribe hasta que Eugenia contesta.
4. [[60 - Replicar desde cero]] — la receta para armarlo de nuevo en otra cuenta.

---

## Mapa de notas

### Meta (Facebook / WhatsApp)
- [[10 - Meta - Business Manager, WABA y número]]
- [[11 - Meta - App Kontrol]]
- [[12 - Meta - Tokens y permisos]]
- [[13 - Coexistencia]]
- [[14 - Webhooks de WhatsApp]]

### Cloudflare
- [[20 - Cloudflare - Cuenta, Workers y R2]]
- [[21 - Worker marketing-ig-scheduler (Eugenia)]]
- [[22 - Worker eugenia-mail-recuperacion]]
- [[23 - Worker eugenia-puerta-r2]]
- [[24 - R2 - Mapa de claves]]
- [[25 - Secretos y variables]]

### Eugenia (el cerebro)
- [[30 - Eugenia - Cerebro y modelos]]
- [[31 - Eugenia - Prompt de venta]]
- [[32 - Eugenia - Reglas post-proceso]]
- [[33 - Eugenia - Modo dueño]]
- [[34 - Eugenia - Voz y notas de voz]]

### Pipelines (flujos de punta a punta)
- [[40 - Pipeline segundo a segundo - mensaje entrante]]
- [[41 - Pipeline - Lead desde anuncio Click-to-WhatsApp]]
- [[42 - Pipeline - Comentario en Instagram a mensaje privado]]
- [[43 - Pipeline - Carritos abandonados]]
- [[44 - Pipeline - Alertas al dueño por WhatsApp]]
- [[45 - Pipeline - Reels con botón de WhatsApp]]
- [[46 - Pipeline - Producción y publicación de reels]]

### Frontend, backend y automatizaciones
- [[50 - Frontend - Panel web]]
- [[51 - Backend - PC marketing-agent]]
- [[52 - GitHub Actions]]

### Replicar, operar, arreglar
- [[60 - Replicar desde cero]]
- [[61 - Código de referencia - Worker WhatsApp]]
- [[62 - Checklist de pruebas]]
- [[70 - Errores conocidos y troubleshooting]]
- [[71 - Seguridad y cumplimiento]]
- [[80 - Cronograma del día]]
- [[90 - Glosario]]
- [[98 - Bitácora]]
- [[99 - Pendientes de documentar]]

---

## Datos clave de un vistazo

| Qué | Valor |
|---|---|
| Número de WhatsApp | `+54 9 294 450-8833` (`5492944508833`, Bariloche, AR) |
| Link público | `https://wa.me/5492944508833` |
| Asistente | **Eugenia** ("Eugenia es mi nombre" / "Euge es mi nombre") |
| Negocios / productos | *Ecosistema Hidropónico* → Curso Completo de Hidroponía · *Bonsái en Casa* → Bonsai en casa desde cero (antes «El Arte del Bonsái») |
| Business Manager | `450083674862372` |
| Página FB hidroponía | `615394648318530` |
| Página FB bonsái | `620810857774404` |
| API | WhatsApp **Cloud API** (Graph `v21.0` por defecto) en **coexistencia** con WhatsApp Business App |
| App de Meta | **Kontrol** (token de sistema `META_TOKEN_KONTROL`, creado 29/08/2026) |
| Worker principal | `marketing-ig-scheduler.goldentimeshift.workers.dev` |
| Otros Workers | `eugenia-mail-recuperacion`, `eugenia-puerta-r2` |
| Bucket R2 | `marketing-reels` |
| LLM de las charlas | **Groq** (3 cuentas, 3 modelos en cascada) |
| Venta | Hotmart (checkout `W99083833C` hidroponía, `T97313346W` bonsái) |
| Copia canónica del vault | `tomixrecoil/eugenia-carritos` → `Whapi/` |
