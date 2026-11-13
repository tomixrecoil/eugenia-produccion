"""Elige la PORTADA (miniatura) de un reel ya terminado (pedido de Tomix, 08/11/2026).

Instagram toma de portada el primer fotograma, que lleva una palabra suelta del subtítulo
("quieres", "los") y no dice nada. Acá la IA mira el video TERMINADO (con sus subtítulos) y
elige un cuadro tal cual, sin editarlo ni escribirle nada encima:
  1) en el que el subtítulo que se ve es una palabra CLAVE y concreta (bonsái, raíces, cosecha),
  2) y la imagen es la más llamativa y particular del video.
Se muestrean cuadros de TODO el video (no solo del principio) para no favorecer un tramo.

Devuelve el momento en milisegundos (para `thumb_offset` de Instagram) y el cuadro en JPG
(para la portada de Facebook). Si algo falla devuelve None: el reel sale igual, con la portada
de siempre. No bloquea la producción.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

CUADROS = 48          # cuadros de la hoja de contacto (8 columnas x 6 filas)
FUENTE = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Baloo2-ExtraBold.ttf"


def _duracion(mp4: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                       capture_output=True, text=True, timeout=60)
    return float((p.stdout or "0").strip() or 0)


def _cuadro(mp4: Path, t: float, ancho: int):
    from PIL import Image
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1",
                        "-vf", f"scale={ancho}:-1", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, timeout=60)
    return Image.open(io.BytesIO(p.stdout)).convert("RGB")


def _hoja(mp4: Path, tiempos: list[float]) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    w, h, cols = 216, 384, 8
    filas = (len(tiempos) + cols - 1) // cols
    img = Image.new("RGB", (cols * w, filas * h), "black")
    try:
        f = ImageFont.truetype(str(FUENTE), 40)
    except OSError:
        f = ImageFont.load_default()
    for i, t in enumerate(tiempos):
        im = _cuadro(mp4, t, w).resize((w, h))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 62, 46], fill=(0, 0, 0))
        d.text((5, -2), str(i), font=f, fill=(255, 230, 0))
        img.paste(im, ((i % cols) * w, (i // cols) * h))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=82)
    return b.getvalue()


_PREGUNTA = (
    "La imagen es una hoja de contacto con cuadros numerados de un reel de {tema} YA TERMINADO, muestreados a lo largo "
    "de TODO el video (no favorezcas ningún tramo). Cada cuadro puede tener una palabra de subtítulo en celeste pegada "
    "al video. Elige el cuadro para usar de MINIATURA (portada) tal cual está, sin editarlo. Criterios, en este orden: "
    "1) la palabra del subtítulo que se ve es una palabra CLAVE y concreta (un sustantivo, un número, una técnica, un "
    "resultado: 'bonsái', 'raíces', 'cosecha', '30 días'), NUNCA una palabra de relleno ('los', 'el', 'de', 'que', "
    "'quieres', 'muchos', 'y', 'con'); "
    "2) la imagen es la más llamativa y particular del video: sujeto claro, bien iluminado, nítido, colorido, que dé "
    "ganas de tocarlo; "
    "3) nada de cuadros borrosos, de transición ni con el sujeto cortado; "
    "4) evita los cuadros donde se ve el nombre de usuario, la marca de agua o el logo de OTRA cuenta (no cuenta el "
    "logo verde propio de arriba). "
    'Responde SOLO un JSON: {{"cuadro": N, "palabra_visible": "...", "motivo": "una frase"}}')


def elegir(mp4: Path, nicho: str = "") -> dict | None:
    """{'ms': int, 'palabra': str, 'motivo': str, 'jpg': bytes} o None si no se pudo."""
    try:
        from google.genai import types as gt
        from src import gemini_client
        mp4 = Path(mp4)
        dur = _duracion(mp4)
        if dur < 3:
            return None
        paso = (dur - 1.0) / CUADROS
        tiempos = [round(0.5 + i * paso, 2) for i in range(CUADROS)]
        tema = {"bonsai": "bonsái", "hidroponia": "hidroponía"}.get(nicho, nicho or "plantas")
        modelo = os.getenv("GEMINI_MODEL") or "gemini-3.6-flash"
        hoja = _hoja(mp4, tiempos)
        resp = gemini_client.run(lambda c: gemini_client.generate(
            c, modelo, [gt.Part.from_bytes(data=hoja, mime_type="image/jpeg"), _PREGUNTA.format(tema=tema)]))
        txt = resp.text if hasattr(resp, "text") else str(resp)
        r = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        i = int(r["cuadro"])
        if not 0 <= i < len(tiempos):
            return None
        t = tiempos[i]
        b = io.BytesIO()
        _cuadro(mp4, t, 1080).save(b, "JPEG", quality=90)
        log.info("Portada elegida: %.1f s (cuadro %d), palabra «%s».", t, i, r.get("palabra_visible", ""))
        return {"ms": int(t * 1000), "palabra": str(r.get("palabra_visible") or ""),
                "motivo": str(r.get("motivo") or "")[:200], "jpg": b.getvalue()}
    except Exception as e:  # noqa: BLE001
        log.warning("No pude elegir la portada (%s): el reel sale con la de siempre.", str(e)[:100])
        return None
