# -*- coding: utf-8 -*-
"""Voz Charon de Google AI Studio (Gemini TTS) — la del sistema B.

Por qué existe
--------------
El sistema A usa Antonio de ElevenLabs. El B usa Charon. Es la segunda —y última—
diferencia entre los dos, así que tiene que poder correr solo, sin pegar nada a mano en
AI Studio: los reels salen a las 6 de la mañana con la computadora apagada.

Lo que NO se hace acá, a propósito
----------------------------------
NO se le manda ningún prompt de estilo a Charon: solo el texto del guion, pelado. Si se
le agregan instrucciones de tono, las LEE EN VOZ ALTA y arruina el audio.

Las tres cuentas
----------------
Se prueban en orden (GEMINI_API_KEY, _2, _3). Cada cuenta tiene su propia cuota diaria,
así que si una se agota se sigue con la siguiente en vez de perder el reel.

Formato
-------
La API devuelve PCM crudo de 24 kHz, 16 bits, mono — NO un archivo de audio. Sin
envolverlo en una cabecera WAV, ffmpeg lo lee como ruido blanco.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path

from src.logging_setup import get_logger

log = get_logger()

VOZ = "Charon"
# El de la nota de Tomix primero; el 2.5 queda de respaldo porque el 3.1 es preview y
# puede desaparecer sin aviso.
MODELOS = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
SAMPLE_RATE = 24000


def _claves() -> list[str]:
    """Las 3 cuentas de AI Studio, en orden, sin vacías ni repetidas."""
    import os
    out = []
    for n in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3",
              "GEMINI_API_KEY_4", "GEMINI_API_KEY_5"):
        v = (os.getenv(n) or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def _a_wav(pcm: bytes, destino: Path) -> Path:
    """Envuelve el PCM crudo en un WAV. Sin esto ffmpeg oye ruido blanco."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # 16 bits
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return destino


def sintetizar(texto: str, destino: Path, voz: str = VOZ, seed: int | None = None) -> Path:
    """Convierte el guion en audio con Charon. Devuelve el WAV.

    Lanza RuntimeError si NINGUNA cuenta pudo: el que llama decide si descarta el reel.
    Nunca devuelve un archivo vacío o a medias.

    `seed`: cada frase de un mismo reel se sintetiza en una llamada INDEPENDIENTE (ver
    sintetizar_con_timing) y sin semilla el timbre no es estable entre ellas — el reel
    suena con una voz que muta. Pasando la MISMA seed en todas las frases de un video se
    fija ese aspecto aleatorio de la generación; sigue siendo Google, no ElevenLabs, así
    que no es garantía absoluta, pero es el mecanismo que ofrece la propia API para esto.
    """
    texto = (texto or "").strip()
    if not texto:
        raise RuntimeError("guion vacío: no hay nada que decir")

    ultimo = None
    for i, clave in enumerate(_claves(), 1):
        for modelo in MODELOS:
            try:
                pcm = _generar(texto, clave, modelo, voz, seed)
                p = _a_wav(pcm, Path(destino))
                log.info("Voz Charon por %s (cuenta %d) — %.1f s", modelo, i,
                         len(pcm) / (SAMPLE_RATE * 2))
                return p
            except Exception as e:  # noqa: BLE001
                ultimo = e
                log.warning("Charon: cuenta %d / %s falló (%s)", i, modelo, str(e)[:110])
    raise RuntimeError(f"ninguna cuenta de AI Studio pudo generar la voz: {str(ultimo)[:200]}")


def _generar(texto: str, clave: str, modelo: str, voz: str = VOZ, seed: int | None = None) -> bytes:
    """UN pedido a Google con una cuenta y un modelo dados. Devuelve el PCM crudo."""
    from google import genai
    from google.genai import types

    cli = genai.Client(api_key=clave)
    cfg_kwargs = dict(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
            )
        ),
    )
    if seed is not None:
        cfg_kwargs["seed"] = seed
    r = cli.models.generate_content(
        model=modelo,
        # Solo el texto. Ninguna instrucción de estilo: las leería en voz alta.
        contents=texto,
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    pcm = r.candidates[0].content.parts[0].inline_data.data
    if not pcm or len(pcm) < 4000:   # < ~0,08 s: vino cortado
        raise RuntimeError(f"audio demasiado corto ({len(pcm or b'')} bytes)")
    return pcm


# ---------------------------------------------------------------------------
# SINCRONIZACIÓN DE SUBTÍTULOS
# ---------------------------------------------------------------------------
# ElevenLabs devuelve el timing real de CADA carácter, así que los subtítulos salen
# clavados. Charon devuelve un audio y nada más. El primer intento repartió el tiempo
# suponiendo que todas las palabras duran igual — y no: hay pausas en las comas, frases
# que se leen rápido y otras lentas. Sobre 50 segundos el subtítulo terminaba corrido
# varios segundos del audio.
#
# Hasta el 04/11 se sintetizaba FRASE POR FRASE (14-27 pedidos por reel) para medir cada
# clip. Eso hacía que la voz cambiara de tono entre frases, y cuando una cuenta se quedaba
# sin cupo a mitad del reel seguía con otra y hasta con otro modelo (Tomix: "parece que se
# cambia de voz todo el tiempo"). Ahora: UN pedido con el guion entero, una cuenta y un
# modelo fijos, y el tiempo de cada frase sale de las PAUSAS del audio (silencedetect):
# cada corte va a la pausa más cercana a donde debería caer. Ver analisis/VOZ_CHARON.md.
import re as _re
import subprocess as _sp


def _frases(texto: str) -> list[str]:
    """Corta el guion en frases por punto, signos de cierre y comas largas."""
    t = _re.sub(r"\s+", " ", (texto or "").strip())
    partes, buf = [], ""
    for tramo in _re.split(r"(?<=[.!?])\s+", t):
        tramo = tramo.strip()
        if not tramo:
            continue
        # Las frases muy largas se parten en la coma para que ningún bloque supere
        # los ~90 caracteres: cuanto más corto el tramo, más fino el sincronismo.
        if len(tramo) > 90 and "," in tramo:
            for sub in _re.split(r"(?<=,)\s+", tramo):
                if buf and len(buf) + len(sub) < 90:
                    buf += " " + sub
                else:
                    if buf:
                        partes.append(buf)
                    buf = sub
            if buf:
                partes.append(buf); buf = ""
        else:
            partes.append(tramo)
    return [p for p in partes if p.strip()]


# Ritmo de Charon en español (caracteres por segundo, medido en reels reales): sirve para
# descartar un audio que vino cortado y para estimar dónde cae cada frase.
CARACTERES_POR_SEG = 15.0


def _silencios(wav: Path) -> list[tuple[float, float]]:
    """Las pausas del audio como (inicio, fin), de ffmpeg silencedetect."""
    p = _sp.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af",
                 "silencedetect=noise=-35dB:d=0.12", "-f", "null", "-"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
    ini, out = None, []
    for linea in p.stderr.splitlines():
        m = _re.search(r"silence_start:\s*([\d.]+)", linea)
        if m:
            ini = float(m.group(1))
            continue
        m = _re.search(r"silence_end:\s*([\d.]+)", linea)
        if m and ini is not None:
            out.append((ini, float(m.group(1))))
            ini = None
    return out


def _cortes_por_pausas(frases: list[str], dur: float, silencios: list[tuple[float, float]]):
    """[(inicio, fin)] de cada frase. Cada corte va a la pausa más cercana a donde debería
    caer según los caracteres; sin pausa razonable cerca, a la posición estimada."""
    habla_ini, habla_fin = 0.0, dur
    sil = list(silencios)
    if sil and sil[0][0] <= 0.05:
        habla_ini = sil.pop(0)[1]
    if sil and sil[-1][1] >= dur - 0.05:
        habla_fin = sil.pop()[0]
    largo = max(habla_fin - habla_ini, 0.1)
    total = sum(len(f) for f in frases) or 1
    tramos, prev_fin, acum = [], habla_ini, 0
    for k, fr in enumerate(frases):
        acum += len(fr)
        if k == len(frases) - 1:
            tramos.append((prev_fin, habla_fin))
            break
        esperado = habla_ini + largo * acum / total
        margen = max(1.2, 0.5 * largo * len(fr) / total)
        candidatos = [(abs((a + b) / 2 - esperado), a, b) for a, b in sil
                      if a > prev_fin + 0.2 and abs((a + b) / 2 - esperado) <= margen]
        if candidatos:
            _, a, b = min(candidatos)
            tramos.append((prev_fin, a))
            prev_fin = b
            sil = [x for x in sil if x[0] > b]
        else:
            tramos.append((prev_fin, esperado))
            prev_fin = esperado
    return tramos


def _whisper(wav: Path):
    """Las palabras del audio con su inicio y fin, de Whisper en Cloudflare (la ruta
    /whisper de la puerta, plan gratis). None si no hay puerta (la PC) o si falla."""
    import json
    import os
    import urllib.request
    url = (os.getenv("PUERTA_R2_URL") or "").strip().rstrip("/")
    clave = (os.getenv("PUERTA_R2_KEY") or "").strip()
    if not (url and clave):
        return None
    mp3 = wav.with_name(wav.stem + "_whisper.mp3")
    p = _sp.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-ac", "1", "-ar", "16000",
                 "-b:a", "32k", str(mp3)], capture_output=True)
    if p.returncode != 0 or not mp3.exists():
        return None
    try:
        req = urllib.request.Request(f"{url}/whisper", data=mp3.read_bytes(), method="POST")
        req.add_header("x-clave", clave)
        req.add_header("user-agent", "eugenia-produccion/1.0")   # sin esto Cloudflare corta (1010)
        req.add_header("content-type", "audio/mpeg")
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("Whisper no respondió (%s): uso los cortes por pausas", str(e)[:100])
        return None
    finally:
        mp3.unlink(missing_ok=True)
    palabras = d.get("words") or []
    return palabras if d.get("ok") and palabras else None


def _sin_tildes(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", t.lower())
    return _re.sub(r"[^a-z0-9ñ]", "", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def _alinear_whisper(texto: str, palabras: list[dict]):
    """Alignment por letra a partir de las palabras de Whisper. Las palabras del guion se
    emparejan con las de Whisper por similitud (Whisper puede escribir "100" o "bonsai"
    distinto); las que no coinciden se reparten entre sus vecinas. None si coincide menos
    del 60 %: ahí no es confiable y quedan los cortes por pausas."""
    import difflib
    tramos = [(m.start(), m.end()) for m in _re.finditer(r"\S+", texto)]
    if not tramos:
        return None
    a = [_sin_tildes(texto[i:j]) for i, j in tramos]
    b = [_sin_tildes(str(w.get("word", ""))) for w in palabras]
    tiempos = [None] * len(tramos)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            w = palabras[blk.b + k]
            tiempos[blk.a + k] = (float(w["start"]), float(w["end"]))
    if sum(t is not None for t in tiempos) < 0.6 * len(tramos):
        return None
    # Las que no coincidieron: entre el fin de la anterior y el inicio de la siguiente.
    k = 0
    while k < len(tiempos):
        if tiempos[k] is not None:
            k += 1
            continue
        j = k
        while j < len(tiempos) and tiempos[j] is None:
            j += 1
        desde = tiempos[k - 1][1] if k > 0 else 0.0
        hasta = tiempos[j][0] if j < len(tiempos) else desde + 0.35 * (j - k)
        paso = max(hasta - desde, 0.0) / (j - k)
        for m in range(k, j):
            tiempos[m] = (desde + paso * (m - k), desde + paso * (m - k + 1))
        k = j
    chars, ini, fin = [], [], []
    ultimo = 0.0
    for (i, j), (t0, t1) in zip(tramos, tiempos):
        t0 = max(t0, ultimo)
        t1 = max(t1, t0)
        if chars:                       # el espacio entre palabras
            chars.append(" "); ini.append(ultimo); fin.append(t0)
        n = j - i
        for q, c in enumerate(texto[i:j]):
            chars.append(c)
            ini.append(t0 + (q / n) * (t1 - t0))
            fin.append(t0 + ((q + 1) / n) * (t1 - t0))
        ultimo = t1
    return {"characters": chars, "character_start_times_seconds": ini,
            "character_end_times_seconds": fin}


def sintetizar_con_timing(texto: str, destino: Path, voz: str = VOZ):
    """(wav_completo, alignment). UN solo pedido por reel (una cuenta, un modelo) y el
    tiempo de cada frase sale de las pausas del audio. Si una cuenta o modelo falla, se
    vuelve a empezar ENTERO con la siguiente: nunca se mezclan dentro del mismo reel.

    El alignment tiene el mismo formato que devuelve ElevenLabs, así que
    subtitles.construir_ass() lo usa sin cambiar una línea.
    """
    destino = Path(destino)
    frases = _frases(texto)
    if not frases:
        raise RuntimeError("guion vacío")
    entero = " ".join(frases)
    minimo = 0.45 * len(entero) / CARACTERES_POR_SEG   # menos que esto: vino cortado

    ultimo = None
    for i, clave in enumerate(_claves(), 1):
        for modelo in MODELOS:
            try:
                pcm = _generar(entero, clave, modelo, voz)
                dur = len(pcm) / (SAMPLE_RATE * 2)
                if dur < minimo:
                    raise RuntimeError(f"audio cortado ({dur:.1f} s para {len(entero)} caracteres)")
                _a_wav(pcm, destino)
                # Primero, el tiempo EXACTO de cada palabra con Whisper (Cloudflare). Si no
                # está o no es confiable, los cortes por pausas de abajo.
                palabras = _whisper(destino)
                al = _alinear_whisper(entero, palabras) if palabras else None
                if al:
                    log.info("Voz Charon por %s (cuenta %d) en UN pedido — %.1f s, subtítulos "
                             "por palabra con Whisper", modelo, i, dur)
                    return destino, al
                tramos = _cortes_por_pausas(frases, dur, _silencios(destino))
                chars, ini, fin = [], [], []
                for fr, (a, b) in zip(frases, tramos):
                    n = max(len(fr), 1)
                    for j, c in enumerate(fr):
                        chars.append(c)
                        ini.append(a + (j / n) * (b - a))
                        fin.append(a + ((j + 1) / n) * (b - a))
                    chars.append(" "); ini.append(b); fin.append(b)
                log.info("Voz Charon por %s (cuenta %d) en UN pedido — %.1f s, %d frases "
                         "cortadas por pausas", modelo, i, dur, len(frases))
                return destino, {"characters": chars,
                                 "character_start_times_seconds": ini,
                                 "character_end_times_seconds": fin}
            except Exception as e:  # noqa: BLE001
                ultimo = e
                log.warning("Charon: cuenta %d / %s falló (%s)", i, modelo, str(e)[:110])
    raise RuntimeError(f"ninguna cuenta de AI Studio pudo generar la voz: {str(ultimo)[:200]}")
