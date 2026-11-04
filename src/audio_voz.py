# -*- coding: utf-8 -*-
"""¿Este video tiene alguien hablando, o es solo ambiente?

Por qué existe
--------------
Para clasificar los 720 videos de la fuente hay que saber cuáles tienen narración (se
traducen) y cuáles están mudos con ambiente (se les inventa un guion). Preguntárselo a
Gemini son 720 llamadas y la cuota diaria gratuita no da: ya frenó dos cuentas en una
tarde. Esto lo resuelve local, gratis y en un segundo por video.

Cómo distingue voz de ambiente
------------------------------
Sin librerías nuevas: todo con ffmpeg.

1. CONCENTRACIÓN EN LA BANDA DE VOZ. La voz humana mete casi toda su energía entre 300 y
   3400 Hz (por eso el teléfono suena a voz con solo esa banda). El ambiente de una
   granja —agua, hojas, viento, motores— es de banda ancha y reparte parejo. Se compara
   el volumen del audio filtrado a esa banda contra el volumen total.

2. RITMO SILÁBICO. Hablar produce pausas cortas y constantes: entre 3 y 8 por segundo.
   El ambiente es continuo. Se cuentan los silencios breves con silencedetect.

Ninguna de las dos alcanza sola —una música con voz cantada dispara la primera; un motor
intermitente dispara la segunda— pero juntas separan bien. Los casos dudosos se marcan
como tales y esos SÍ van a Gemini, que son pocos.

IMPORTANTE: ante la duda devuelve "dudoso", NUNCA "mudo". Equivocarse hacia "mudo"
significa inventarle un guion en español a un video que ya habla en inglés, y publicar
las dos voces pisándose. Ese error ya salió al aire una vez.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from src.logging_setup import get_logger

log = get_logger()

# Umbrales calibrados contra los 39 videos de Agrotonomy que el pipeline ya había
# clasificado (33 con voz, 6 mudos). Medido sobre esa muestra: 31 aciertos, 6 dudosos y
# 2 errores, los DOS en la dirección segura (dijo "voz" a un mudo, nunca al revés).
#
# Se decide por la CONCENTRACIÓN sola. Las pausas por segundo se calculan igual porque
# sirven para revisar a mano, pero NO deciden: en la muestra los mudos daban 0,87-1,00 y
# las voces 0,43-2,00, o sea que se pisan y no separan nada.
CONC_VOZ = 0.62      # por encima = suena a voz
CONC_AMB = 0.46      # por debajo = suena a ambiente
# La franja del medio queda "dudoso" a propósito: es un 15% que resuelve Gemini.


def _ffmpeg(args: list[str]) -> str:
    """Corre ffmpeg y devuelve su salida de log (los filtros escriben en stderr)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", *args],
                       capture_output=True, timeout=180)
    return (r.stderr or b"").decode("utf-8", "ignore")


def _rms(entrada: Path, filtro: str | None, segundos: int) -> float:
    """Volumen medio (dB) del audio, opcionalmente filtrado a una banda."""
    args = ["-t", str(segundos), "-i", str(entrada), "-vn"]
    af = "volumedetect" if not filtro else f"{filtro},volumedetect"
    args += ["-af", af, "-f", "null", "-"]
    out = _ffmpeg(args)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", out)
    return float(m.group(1)) if m else -91.0


def _pausas_por_segundo(entrada: Path, segundos: int) -> float:
    """Cuántos silencios breves hay por segundo. Hablar genera muchos; el ambiente casi
    ninguno. Se mide sobre la banda de voz para que el ruido de fondo no los tape."""
    out = _ffmpeg(["-t", str(segundos), "-i", str(entrada), "-vn",
                   "-af", "highpass=f=300,lowpass=f=3400,silencedetect=n=-32dB:d=0.12",
                   "-f", "null", "-"])
    return len(re.findall(r"silence_start", out)) / max(segundos, 1)


def analizar(video: Path, segundos: int = 30) -> dict:
    """{'clase': 'voz'|'mudo'|'dudoso'|'sin_audio', 'concentracion': …, 'pausas': …}

    `clase='dudoso'` significa: preguntale a Gemini. Es a propósito: es preferible gastar
    una llamada que publicar un reel con dos voces encima.
    """
    video = Path(video)
    try:
        total = _rms(video, None, segundos)
        if total <= -60.0:
            return {"clase": "sin_audio", "concentracion": 0.0, "pausas": 0.0,
                    "detalle": f"silencio total ({total:.0f} dB)"}
        voz = _rms(video, "highpass=f=300,lowpass=f=3400", segundos)
        # Cuánto del volumen sobrevive al filtrar solo la banda de voz. En dB la resta
        # es una razón; se normaliza a 0-1 sobre un rango de 12 dB, que es lo que separa
        # en la práctica una voz de un ambiente ancho.
        conc = max(0.0, min(1.0, 1.0 - (total - voz) / 12.0))
        pausas = _pausas_por_segundo(video, segundos)

        if conc >= CONC_VOZ:
            clase = "voz"
        elif conc <= CONC_AMB:
            clase = "mudo"
        else:
            clase = "dudoso"
        return {"clase": clase, "concentracion": round(conc, 3),
                "pausas": round(pausas, 2), "db_total": round(total, 1),
                "detalle": f"conc={conc:.2f} pausas={pausas:.2f}/s"}
    except Exception as e:  # noqa: BLE001
        # Si algo falla NO se adivina: va a Gemini.
        log.warning("No pude analizar %s (%s) -> dudoso.", video.name, str(e)[:80])
        return {"clase": "dudoso", "concentracion": 0.0, "pausas": 0.0,
                "detalle": f"error: {str(e)[:60]}"}
