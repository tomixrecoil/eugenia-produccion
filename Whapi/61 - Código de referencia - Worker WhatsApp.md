---
tags: [whapi, codigo, replicar]
---

# Código de referencia — Worker de WhatsApp

> [!important] Qué es y qué no es
> Es una **implementación nueva y completa** del pipeline de
> [[40 - Pipeline segundo a segundo - mensaje entrante]], escrita para que cualquiera pueda
> replicar el sistema. **No es una copia** del Worker en producción (`marketing-agent/cloudflare-worker`,
> que está solo en la PC). Está **probada** contra Meta, Groq y R2 simulados.

## Archivos (en este vault)

```
codigo/worker-referencia/
├── wrangler.toml          binding R2, cron */10, variables
├── package.json           npm test / deploy / tail
├── src/index.js           el Worker (~330 líneas)
└── test/simulacion.mjs    prueba de punta a punta sin internet
```

## Qué implementa

| Paso del pipeline | Función |
|---|---|
| Verificación `hub.challenge` | `fetch` → `GET /webhook/whatsapp` |
| Firma `X-Hub-Signature-256` (comparación de tiempo constante) | `hmacHex`, `igualSeguro` |
| 200 inmediato + trabajo en segundo plano | `ctx.waitUntil(despachar(...))` |
| Varios `entry/changes/messages` por POST | `despachar` |
| Dedupe por `wamid` | `wa/vistos/<wamid>` en R2 |
| Modo dueño (`stock`, `pausa <tel>`, `reanudar <tel>`) | `ordenDueno` + secreto `OWNER_NUMBERS` |
| Historial por contacto | `wa/conv/<wa_id>.json` |
| Origen del lead (anuncio CTWA) | `msg.referral` → `conv.origen` |
| Nicho por historial / anuncio / palabras clave | `detectarNicho` |
| Pausa si Tomix escribió desde el celular (coexistencia) | `procesarEco` → `pausado_hasta` 12 h |
| Leído + "escribiendo…" | `marcarLeidoYEscribiendo` |
| Saludo por hora local y país | `contextoLocal` |
| Prompt con `{{PRECIO}}`, `{{QUE_INCLUYE}}`, `{{DATOS_COBRO}}`, `[SITUACIÓN]`, catálogo | `armarPrompt` (lee `config/eugenia/venta_<nicho>.txt` y `config/eugenia/<nicho>.json` de R2) |
| Groq: 3 modelos × 3 cuentas, salta ante 429/5xx | `groq` |
| Reglas: sin markdown, precio exacto, sin link en el 1er mensaje, 1 solo link, link aparte | `postProceso` |
| `sck=wa-…` en links de Hotmart | `conOrigen` |
| Envío texto → pausa 1,5 s → link con preview | `procesarMensaje` paso 7 |
| Registro de fallos (131047, etc.) | `procesarEstado` → `wa/fallos.json` |
| Ruta pública `/v/` con guard (solo `reels/*.mp4`) | `fetch` |
| Cron | `scheduled` (vacío, para la cola de IG / seguimientos) |

## Configuración que lee de R2

```
config/eugenia/venta_bonsai.txt        ← copia de prompts/venta_bonsai.txt
config/eugenia/venta_hidroponia.txt
config/eugenia/bonsai.json             ← {"precio":"19.97","descuento":80,"que_incluye":"🎥 +6 horas…",
config/eugenia/hidroponia.json            "datos_cobro":"…","transferencia_ar":"Alias … CBU … Banco … Monto …",
                                          "catalogo":"…"}
```

## Correr la prueba

```bash
cd Whapi/codigo/worker-referencia
```
```bash
npm test
```

Salida esperada (resumen): verificación 200/403, sin firma 401, primer mensaje **sin link**,
segundo con "Son 19.97 USD" (el modelo dijo 20 → regla de precio) y el link **aparte** con
`&sck=wa-euge`, después del eco **no** contesta, `stock` responde al dueño, el 131047 queda en
`wa/fallos.json`, y `/v/wa/clientes.json` da 404.

## Desplegar

```bash
npx wrangler login
```
```bash
npx wrangler secret put WHATSAPP_TOKEN
```
(repetir para `WHATSAPP_PHONE_ID`, `META_APP_SECRET`, `WA_VERIFY_TOKEN`, `GROQ_API_KEY`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`, `OWNER_NUMBERS`)
```bash
npx wrangler deploy
```
URL de webhook resultante: `https://eugenia-whatsapp.<tu-subdominio>.workers.dev/webhook/whatsapp`.

## Límites conocidos de esta referencia

- `wa/conv/<id>.json` se lee-modifica-escribe sin candado: dos mensajes del mismo cliente en el mismo segundo pueden pisarse. Para volumen alto usar **Durable Objects** (uno por `wa_id`) o una cola.
- No transcribe audios ni lee imágenes (responde con el texto `[envió un audio]` como contexto).
- No incluye la publicación de Instagram del cron ni los webhooks de Hotmart/Instagram.
