---
tags: [whapi, eugenia, operacion]
---

# Eugenia — Modo dueño (órdenes por WhatsApp)

Además de vender, Eugenia es la **asistente operativa** de Tomix: él le escribe al mismo
número desde su WhatsApp personal y ella ejecuta tareas del negocio **sin la PC**.

## Órdenes documentadas en el código (✅)

| Orden (ejemplo) | Qué hace | Fuente |
|---|---|---|
| `stock` | Lee `stock/index.json` y responde cuántos reels hay listos por nicho | `armar_stock.py:17` |
| `publicá uno de bonsái` | Toma el primer reel del stock de ese nicho (solo los `arreglado` si aplica) y lo publica (FB/IG vía API de Meta) e informa **con qué voz salió** y si el guion es **inventado** (video mudo) o **traducción** | `armar_stock.py:17,100-102`, `re_voz_stock.py:14`, `producir_stock.py:972` |
| Consultar el registro de fuentes | Lee `fuentes/usadas.json` ("¿ya usamos este video?") | `registro_fuentes.py:48-50` |

## Cómo distingue al dueño de un cliente (🟡/🔵)

El remitente (`messages[0].from`) se compara con el número del dueño (probablemente
`ALERT_WHATSAPP` o una lista propia ❓). Si coincide → *router* de órdenes; si no → flujo de venta.

> [!important] Ventana de 24 h
> Las respuestas de Eugenia a Tomix son mensajes de "servicio" dentro de la ventana que él
> abrió al escribir. Por eso **las alertas** también llegan solo si Tomix le escribió al
> número en las últimas 24 h → [[44 - Pipeline - Alertas al dueño por WhatsApp]].

## Recomendación para replicar (🔵)

- Lista blanca de números dueños en un secreto (`OWNER_NUMBERS=549…,549…`).
- Órdenes por **palabra clave exacta** primero (`stock`, `pausa <tel>`, `reanudar <tel>`), y si no matchea, un LLM con *function calling* limitado a funciones seguras.
- Toda acción con efecto externo (publicar) responde primero con un resumen y pide "sí".
