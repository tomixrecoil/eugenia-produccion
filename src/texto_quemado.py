"""Subtítulos quemados en el video original (23/11, Tomix).

Algunos TikTok fuente traen subtítulos sobreimpresos (en inglés), por ejemplo el perfil de
terrarios @worcesterterrariums. Nuestros subtítulos quedaban encima del texto en inglés.
Acá se detecta si el video trae SUBTÍTULOS y en qué franja, y se calcula la cinta borrosa
(videoedit.filtro_cinta) que los tapa, con nuestros subtítulos encima.

Solo subtítulos (frases, lo que se dice). NO anotaciones sueltas: en hidroponía a veces
ponen el nombre de la planta en inglés en una esquina o al costado; eso no lleva cinta
(Tomix, 23/11).

Modo por nicho (niches/<nicho>.yaml, `cinta_subtitulos`):
  auto    (por defecto) Gemini mira cada video
  siempre cinta aunque no detecte (en la franja de nuestros subtítulos)
  nunca   sin cinta
Si la detección falla, no se pone cinta (el reel sale como siempre).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from src.logging_setup import get_logger

log = get_logger()

PLAY_H = 1920
MARGEN = 0.025      # aire arriba y abajo de lo que hay que tapar
ALTO_MAX = 0.34     # una cinta más alta que esto tapa demasiado video

PROMPT = (
    "Estas imágenes son cuadros del MISMO video vertical, en orden. ¿El video tiene "
    "SUBTÍTULOS sobreimpresos en edición, es decir frases que acompañan lo que se dice o "
    "se cuenta (captions de una o varias líneas, normalmente en el medio o abajo)? "
    "NO cuentan: anotaciones sueltas como el nombre de una planta o un objeto en una esquina "
    "o al costado, flechas o etiquetas puntuales, carteles o letras que son parte de la "
    "escena filmada, ni marcas de agua o nombres de usuario. Respondé SOLO un JSON, sin nada "
    'más: {"subtitulos": true|false, "cajas": [{"cuadro": <n desde 1>, "box_2d": [ymin, '
    'xmin, ymax, xmax]}]} con una caja por cada cuadro donde se ven subtítulos, en '
    "coordenadas normalizadas 0-1000 que encierren justo el texto. Si no hay subtítulos: "
    '{"subtitulos": false}.'
)


def _cuadros(video: Path, n: int = 6) -> list[bytes]:
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True).stdout or 0)
    out = []
    for i in range(n):
        t = 0.5 + (max(dur - 1.0, 0.5)) * i / max(n - 1, 1)
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=540:-2", "-f", "image2pipe",
                            "-vcodec", "mjpeg", "-"], capture_output=True)
        if r.stdout:
            out.append(r.stdout)
    return out


def detectar(video: Path, model: str = "gemini-2.5-flash") -> tuple[float, float] | None:
    """(arriba, abajo) de la franja con subtítulos quemados, o None si no hay o no se pudo ver."""
    from google.genai import types
    from src import gemini_client
    cuadros = _cuadros(video)
    if not cuadros:
        return None

    def call(client):
        partes = [types.Part.from_bytes(data=c, mime_type="image/jpeg") for c in cuadros]
        return (gemini_client.generate(client, model, [*partes, PROMPT]).text or "").strip()

    try:
        txt = gemini_client.run(call)
        m = re.search(r"\{.*\}", txt, re.S)
        d = json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        log.warning("No pude ver si el video trae subtítulos quemados (%s): sin cinta.", str(e)[:120])
        return None
    if not d.get("subtitulos"):
        log.info("El video no trae subtítulos quemados: sin cinta.")
        return None
    try:
        cajas = [c["box_2d"] for c in d.get("cajas", []) if len(c.get("box_2d", [])) == 4]
        a = min(float(c[0]) for c in cajas) / 1000
        b = max(float(c[2]) for c in cajas) / 1000
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= a < b <= 1):
        return None
    log.info("Subtítulos quemados en el original: franja %.2f-%.2f del alto.", a, b)
    return a, b


def _franja_nuestra(niche) -> tuple[float, float]:
    """Dónde quedan nuestros subtítulos (subtitles.construir_ass: Alignment 2, MarginV
    desde abajo sobre 1920 de alto)."""
    base = 1 - niche.subtitle_margin_v / PLAY_H
    alto = niche.subtitle_font_size * 0.95 / PLAY_H
    return base - alto, base + 0.01


def cinta_para(video_fuente: Path, niche, model: str = "gemini-2.5-flash") -> tuple[float, float] | None:
    """(y, alto) de la cinta para videoedit.burn_subtitles, o None si no va."""
    modo = (getattr(niche, "cinta_subtitulos", "auto") or "auto").lower()
    if modo == "nunca":
        return None
    suya = detectar(video_fuente, model)
    if suya is None and modo != "siempre":
        return None
    a, b = _franja_nuestra(niche)
    if suya:
        # La cinta cubre lo suyo y lo nuestro juntos; si quedan muy lejos, solo lo suyo
        # (nuestros subtítulos van donde siempre).
        ua, ub = min(a, suya[0]), max(b, suya[1])
        a, b = (ua, ub) if ub - ua <= ALTO_MAX else suya
    a, b = max(0.0, a - MARGEN), min(1.0, b + MARGEN)
    log.info("Cinta borrosa: %.2f-%.2f del alto.", a, b)
    return round(a, 3), round(b - a, 3)
