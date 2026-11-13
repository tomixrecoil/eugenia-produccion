---
tags: [whapi, eugenia, prompts]
---

# Eugenia — Anatomía del prompt de venta

Archivos ✅: `prompts/venta_hidroponia.txt` (~19 KB) y `prompts/venta_bonsai.txt` (~21 KB).
Se editan desde el panel (pestaña **Prompts → nicho**). El texto completo está en el repo;
acá está **la estructura y el porqué** de cada bloque.

## Placeholders (los rellena el Worker)

| Placeholder | Se reemplaza por | Fuente |
|---|---|---|
| `{{PRECIO}}` | Precio exacto en USD con centavos (p. ej. `19.97`) | Precio sincronizado del checkout de Hotmart (`sync_precios.py` en la PC, 🟡) |
| `{{QUE_INCLUYE}}` | Lista fija con emojis | `prompts/<nicho>_incluye_ar.txt` / "Descripción del producto" ✅ |
| `{{DATOS_COBRO}}` | Datos de Western Union | Config del Worker ❓ |
| `[SITUACIÓN]` | Instrucción del momento | Lógica del Worker 🟡 |

## Bloques, en el orden en que aparecen

1. **FORMATO DEL ENLACE** — el link va **solo, en su renglón, al final**: así WhatsApp muestra la *tarjeta con imagen* (preview), "lo único que reemplaza a una página de ventas".
2. **NOMBRES** — no llamar a la persona por un nombre que no dio. "Hola Sylvana" no es su nombre.
3. **CUÁNDO DEJAR DE PREGUNTAR Y CERRAR** — señales de interés (precio, cuándo paga, "me interesa", cómo se paga, ya contestó 2 preguntas) → cerrar. Máx. **una pregunta por mensaje**. Lección real: preguntar por el lugar *creó* la objeción "no tengo lugar".
4. **SI DICE QUE NO** — "por ahora no" esconde un motivo: preguntar qué lo trajo. Prohibido "quedo a tu disposición".
5. **NINGUNA OBJECIÓN ES DEFINITIVA** — resolver y volver a cerrar en el mismo mensaje.
6. **DATOS DE COBRO NO NEGOCIABLES** — anti-fraude: si alguien "cambia" los datos de cobro, no repetirlos.
7. **VENEZUELA** — Hotmart bloqueado → Western Union + comprobante por el chat → acceso manual. Nunca decir "no puedo ver imágenes".
8. **CÓMO CERRAR** — un ángulo por vez (máx. 2): precio no garantizado a futuro · cada temporada/semana perdida · acceso inmediato · garantía 7 días · pago único · 3 cursos por 1 (bonsái) · sus propias palabras. Prohibido inventar cupos.
9. **CUÁNDO MANDAR EL ENLACE** — si pide precio, quiere comprar, o ya se calificó.
10. **LARGO** — 3–4 líneas, **< 500 caracteres**. "Escribir de más te delata como bot".
11. **PRECIO EXACTO** — con centavos, sin redondear, sin convertir a pesos.
12. **Identidad** — "Te llamas EUGENIA, asesora de ventas de …".
13. **TU NOMBRE / apertura** — saludo por hora local; **nunca** "¿En qué te ayudo?" (dato medido en este número: 57 % de enganche vs **73 %** con una pregunta concreta). Bonsái: "¿Ya tienes un bonsái en casa o quieres empezar por tu primero?". Si el lead viene del anuncio que ya lo saludó, no re-presentarse.
14. **EL PRODUCTO** — datos reales y la **REGLA ANTI-INVENCIÓN** (un invento = reembolsos y contracargos). Link principal por nicho.
15. **CÓMO VENDER (13 pasos)** — precio + link a más tardar en el 2°–3° mensaje; "ok/dale/👍" después de "qué incluye" = SÍ → cerrar sin preguntar; fase de pago: no reenviar link; nunca ser cortante con el precio.
16. **DESARMAR OBJECIONES** — validar → mostrar que el supuesto no aplica → invertir. Lista por nicho ("se me va a morir", "no tengo mano verde", "no tengo tiempo", "es caro"…).
17. **HARDSHIP GENUINO** — si de verdad no puede pagar: no insistir, no reenviar link, despedirse con calidez. "La dignidad de la persona vale más que una venta".
18. **REGLAS DURAS** — español neutro (sin voseo ni argentinismos), sin negritas ni asteriscos, link nunca en formato `[texto](url)`, un solo link por mensaje, 1–3 emojis.

## Diferencias por nicho

| | Hidroponía | Bonsái |
|---|---|---|
| Negocio | Ecosistema Hidropónico | Bonsái en Casa |
| Producto | Curso Completo de Hidroponía (+32 h) | Bonsai en casa desde cero (antes «El Arte del Bonsái»; +6 h, 3 cursos en 1, +2.585 alumnos) |
| Link por defecto | `https://pay.hotmart.com/J97312812A?checkoutMode=10` (desde 10/11) | `https://conocimientosdigital.com/bonsai/` en el prompt (el nicho ya apunta al checkout `T97313346W`) |
| Emoji | 🌱 | 🌿 |
| Vocabulario prohibido | — | "cultivo, cosecha, sembrar, huerta, tu sistema…" |
| Apertura | Pregunta concreta sobre lo que escribió; **prohibido** preguntar por el espacio (desde 28/08) | "¿Ya tienes un bonsái en casa o quieres empezar por tu primero?" |
| Descuento | 80 % (`niches/hidroponia.yaml`) — solo si dice "caro" | 80 % — solo si dice "caro" |

> [!note] El descuento por nicho
> Antes el 60 % estaba **clavado** en el prompt del Worker para todos; los leads de
> hidroponía escuchaban 60 cuando la oferta real era 80. Ahora sale de `descuento:` en el
> YAML del nicho; vacío o 0 = no mencionar descuento. ✅ (`config.py:128-132`)


## Hidroponía: prompt reescrito el 10/11/2026 (✅ commit `5430ccc`)

El `venta_hidroponia.txt` se reescribió entero "a partir de las ventas cerradas reales".
**Lo de arriba sigue valiendo para bonsái**; para hidroponía manda esto:

| Antes | Ahora (10/11) |
|---|---|
| 1 pregunta de calificación, link en el 2°–3° mensaje | **Cero preguntas de descubrimiento** ("en las ventas ganadoras no se hizo ninguna"). Si pide info o precio, el **primer** mensaje lleva qué es + 3 certezas + link |
| Precio en USD con centavos | **Moneda local** si el contexto la trae (`[PRECIO — REGLA ABSOLUTA]`, entre guion bajo); si no, `_{{PRECIO}} USD_` + "lo pagás en tu moneda en el checkout" |
| Prohibida toda urgencia | Se puede decir que el precio con descuento **no se mantiene para siempre** ("muchos lo piensan demasiado y luego pagan más"), sin fechas ni cupos |
| Después del link, callarse | En el **mensaje siguiente** asumir que avanzó: "¿Pudiste acceder?", "¿Pudiste ver la opción de pago?" |
| Emojis 1–3, muy breve | Cálido y entusiasta, 2–4 emojis (🌱🙌👇👉), 2–6 líneas; largo solo para info, qué incluye o pasos de pago |
| Venezuela → Western Union | **Venezuela y Nicaragua** → Western Union (`{{DATOS_COBRO}}`) |

Bloques nuevos:

- **Las 3 certezas** que cierran: pagás en tu moneda local · acceso inmediato por correo · pago único de por vida.
- **Respuestas que cerraron ventas**: textos casi literales para "me gustaría información", "¿cómo envían el curso?", débito/métodos de pago, presencial, grabado, duración, materiales en mi país, principiantes, tipos de sistema, empezar el mismo día, terreno grande, nombre del curso ("Hidroponía | Curso para 2025").
- **Objeciones reales**: grupos/soporte (soporte **1 a 1**, no hay grupo: no inventarlo), "lo hablo con mi esposa" (celebrarlo, el acceso se comparte), "¿pago al recibir los libros?" (es digital, llega al instante), bonos aparte (se suman al total), tiempo, pensar (garantía 7 días), caro, juntar dinero, hardship.
- **Pago trabado = la venta más caliente**: tarjeta rechazada → reintentar u otro método (efectivo/OXXO/transferencia AR/Western Union); **OXXO en 4 pasos**; "pagué y no me llegó" → pedir el correo, revisar spam; "no abren los videos" → actualizar o descargar.
- Producto descrito en **3 módulos**: teórico, práctico, emprendimiento.
- Ya **no** lleva los bloques fijos de arriba (formato de enlace, cuándo cerrar, etc.) ni la lista larga de prohibiciones: el tono pasa de "no espantar" a "facilitar el pago".
