---
tags: [whapi, pruebas, operacion]
---

# Checklist de pruebas

## Después de cada cambio en el Worker o el prompt

| # | Prueba | Resultado esperado |
|---|---|---|
| 1 | `npm test` (simulación) | Todas las líneas como en [[61 - Código de referencia - Worker WhatsApp#Correr la prueba]] |
| 2 | Meta → "Verificar y guardar" webhook | OK |
| 3 | Escribir "Hola, quiero aprender las técnicas del Bonsái" desde un número de prueba | En 2–8 s: saludo por hora local, **sin** presentarse largo, **una** pregunta concreta, **sin** link |
| 4 | Preguntar "¿cuánto sale?" | Precio **exacto** (en moneda local si el contexto la trae) + link **solo en su renglón**, con tarjeta de preview y `sck=wa-…` |
| 4b | (Hidroponía) "Me gustaría información" | En el **primer** mensaje: qué es + 3 certezas + link. Sin preguntas de descubrimiento. En el siguiente: "¿Pudiste acceder?" |
| 4c | (Hidroponía) "Quiero pagar en OXXO" | Link + los 4 pasos de OXXO |
| 5 | Decir "está caro" | Menciona el descuento del nicho una vez, sin urgencia, y reencuadra |
| 6 | Decir "no tengo trabajo, de verdad no puedo" | Despedida cálida, **sin** link ni precio |
| 7 | Escribir "hola Sylvana" | No la llama Sylvana |
| 8 | Contestar a mano desde la app del celular | Eugenia **no** responde los siguientes mensajes de ese cliente (pausa) |
| 9 | Desde el número dueño: `stock` | Responde conteo por nicho |
| 10 | Mandar 2 mensajes seguidos rápido | No hay respuestas duplicadas |
| 11 | `curl https://<worker>/v/wa/clientes.json` | 404 |
| 12 | Panel de Meta → WhatsApp Manager → Información | Calidad del número verde |
| 13 | `npx wrangler tail` mientras se prueba | Sin `WA error` ni `despachar` |

## Comandos útiles

```bash
npx wrangler tail marketing-ig-scheduler --format pretty
```
```bash
curl "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" -H "Authorization: Bearer <TOKEN>"
```
```bash
curl "https://graph.facebook.com/v21.0/<PHONE_ID>?fields=display_phone_number,verified_name,quality_rating,messaging_limit_tier,platform_type" -H "Authorization: Bearer <TOKEN>"
```
