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
| Link por defecto | `https://pay.hotmart.com/W99083833C?checkoutMode=10` | `https://conocimientosdigital.com/bonsai/` |
| Emoji | 🌱 | 🌿 |
| Vocabulario prohibido | — | "cultivo, cosecha, sembrar, huerta, tu sistema…" |
| Apertura | Pregunta concreta sobre lo que escribió; **prohibido** preguntar por el espacio (desde 28/08) | "¿Ya tienes un bonsái en casa o quieres empezar por tu primero?" |
| Descuento | 80 % (`niches/hidroponia.yaml`) — solo si dice "caro" | 80 % — solo si dice "caro" |

> [!note] El descuento por nicho
> Antes el 60 % estaba **clavado** en el prompt del Worker para todos; los leads de
> hidroponía escuchaban 60 cuando la oferta real era 80. Ahora sale de `descuento:` en el
> YAML del nicho; vacío o 0 = no mencionar descuento. ✅ (`config.py:128-132`)
