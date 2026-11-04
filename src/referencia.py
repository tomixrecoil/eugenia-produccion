"""Referencia de lo que funcionó: los reels ganadores de cada cuenta (pedido de Tomix,
19/10/2026).

Las cuentas de Gemini (API) no tienen memoria propia: cada pedido arranca de cero, con
cualquiera de las 6 keys. Por eso la referencia viaja como INSTRUCCIÓN DE SISTEMA en
cada pedido que escribe un guion o un copy. Así la tienen todas las cuentas, siempre.

Son DATOS para tener en cuenta, no la tarea: la tarea (y su formato) sigue saliendo de
prompts/. El contenido vive en prompts/<nicho>_referencia_ganadores.txt y se arma desde
analisis/GANADORES_IG_*.md.
"""
from __future__ import annotations

from pathlib import Path

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

_ENCABEZADO = (
    "CONTEXTO DE REFERENCIA (no es la tarea): abajo están los reels que MEJOR funcionaron "
    "en esta cuenta de Instagram, medidos por guardados, compartidos, comentarios, likes "
    "y vistas, con su guion real, su copy y por qué funcionaron. Usalos para entender qué "
    "le funciona a esta audiencia (temas, ganchos, densidad de datos, cómo se vende el "
    "curso). No copies frases textuales ni inventes datos que no estén en el material del "
    "video. La tarea concreta y su formato vienen en el mensaje del usuario y mandan sobre "
    "esto.\n\n"
)


def ganadores(nicho: str) -> str:
    """El texto de referencia del nicho, o '' si no hay archivo."""
    if not nicho:
        return ""
    f = PROMPTS / f"{nicho}_referencia_ganadores.txt"
    try:
        return f.read_text(encoding="utf-8").strip() if f.is_file() else ""
    except OSError:
        return ""


def como_sistema(nicho: str) -> str | None:
    """La referencia lista para ir como system_instruction, o None si no hay."""
    txt = ganadores(nicho)
    return (_ENCABEZADO + txt) if txt else None
