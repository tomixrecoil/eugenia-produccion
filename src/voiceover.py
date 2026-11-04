"""
Voz con ElevenLabs: resuelve la voz por nombre (ej. "Antonio") o voice_id,
y sintetiza un guión en español a un mp3.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

from src.logging_setup import get_logger

log = get_logger()

API = "https://api.elevenlabs.io/v1"

# Voz premade gratis (Antoni) usada como respaldo si la voz elegida requiere plan pago.
FREE_FALLBACK_VOICE = "ErXwobaYiN019PkySvjV"

# Voz por defecto del sistema: profesional latina, la que usa Tomix.
# (El fallback de arriba se llama "Antoni" — parecido pero NO es la misma.)
VOZ_POR_DEFECTO = "htFfPSZGJwjBv1CL0aMD"   # Antonio – Confident Conversational Latino

# ElevenLabs solo acepta speed entre 0.7 y 1.2 en voice_settings. Para ir más rápido
# que eso hay que acelerar el mp3 después con ffmpeg (y correr los subtítulos igual).
SPEED_MIN_API, SPEED_MAX_API = 0.7, 1.2


def partir_velocidad(speed: float) -> tuple[float, float]:
    """Reparte la velocidad pedida entre lo que puede hacer la API (suena mejor) y
    lo que hay que hacer con ffmpeg. Devuelve (nativa, resto_para_ffmpeg)."""
    speed = max(0.5, min(3.0, float(speed or 1.0)))
    nativa = max(SPEED_MIN_API, min(SPEED_MAX_API, speed))
    return nativa, speed / nativa


def eleven_keys() -> list[str]:
    """Todas las API keys de ElevenLabs configuradas, en orden de prioridad."""
    out = []
    for name in ("ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY_2",
                 "ELEVENLABS_API_KEY_3", "ELEVENLABS_API_KEY_4",
                 "ELEVENLABS_API_KEY_5"):
        v = (os.getenv(name) or "").strip()
        if v:
            out.append(v)
    return out


def resolve_voice_id(api_key: str, voice: str) -> str:
    """Si 'voice' ya parece un voice_id (20 chars alfanum), lo devuelve.
    Si es un nombre, lo busca en la lista de voces de la cuenta."""
    voice = (voice or "").strip()
    # Heurística: los voice_id de ElevenLabs son ~20 chars sin espacios.
    if len(voice) >= 18 and " " not in voice and voice.lower() != "antonio":
        return voice
    r = requests.get(f"{API}/voices", headers={"xi-api-key": api_key}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs /voices falló [{r.status_code}]: {r.text[:200]}")
    voices = r.json().get("voices", [])
    for v in voices:
        if v.get("name", "").strip().lower() == voice.lower():
            return v["voice_id"]
    disponibles = ", ".join(v.get("name", "?") for v in voices) or "(ninguna)"
    raise RuntimeError(
        f"No encontré la voz '{voice}' en tu cuenta de ElevenLabs. "
        f"Voces disponibles: {disponibles}. Usá uno de esos nombres o pegá el voice_id."
    )


def _tts(voice_id: str, text: str, model: str, api_key: str,
         speed: float = 1.0) -> requests.Response:
    return requests.post(
        f"{API}/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
        json={
            "text": text,
            "model_id": model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                               "style": 0.0, "use_speaker_boost": True,
                               "speed": speed},
        },
        timeout=180,
    )


def _tts_timestamps(voice_id: str, text: str, model: str, api_key: str,
                    speed: float = 1.0) -> requests.Response:
    """Igual que _tts pero por el endpoint que además devuelve el tiempo EXACTO de cada
    carácter. Con eso se arman subtítulos perfectamente sincronizados sin transcribir."""
    return requests.post(
        f"{API}/text-to-speech/{voice_id}/with-timestamps",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                               "style": 0.0, "use_speaker_boost": True,
                               "speed": speed},
        },
        timeout=180,
    )


def acelerar_audio(audio: Path, factor: float, out: Path) -> Path:
    """Acelera el audio con ffmpeg SIN cambiarle el tono. atempo solo acepta hasta 2.0
    por filtro, así que si hace falta más se encadenan varios."""
    import subprocess
    if abs(factor - 1.0) < 0.01:
        return audio
    cadena, resto = [], factor
    while resto > 2.0:
        cadena.append("atempo=2.0")
        resto /= 2.0
    while resto < 0.5:
        cadena.append("atempo=0.5")
        resto /= 0.5
    cadena.append(f"atempo={resto:.4f}")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(audio),
           "-filter:a", ",".join(cadena), "-c:a", "libmp3lame", "-q:a", "2", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 or not out.exists():
        log.warning("No pude acelerar la voz (%s) -> la dejo a velocidad normal.",
                    (p.stderr or "")[-160:])
        return audio
    return out


def escalar_alignment(alignment: dict, factor: float) -> dict:
    """Corre los tiempos de cada carácter al acelerar el audio. Sin esto los
    subtítulos quedan desfasados y aparecen tarde."""
    if not alignment or abs(factor - 1.0) < 0.01:
        return alignment
    out = dict(alignment)
    for clave in ("character_start_times_seconds", "character_end_times_seconds"):
        if isinstance(alignment.get(clave), list):
            out[clave] = [t / factor for t in alignment[clave]]
    return out


class VozNoDisponible(RuntimeError):
    """Esta cuenta no puede usar la voz pedida (plan free y voz de biblioteca).

    Existe para que el que llama pueda PROBAR OTRA CUENTA en vez de conformarse con una
    voz distinta. Antes, ante un 402, esta misma función reintentaba con Antoni y
    devolvía eso como si nada: el reel salía con otra voz, la marca sonaba distinta y en
    el log quedaba un warning que nadie mira. Pasó de verdad con dos reels ya publicados.
    """


def synthesize_timed(text: str, api_key: str, voice: str, model: str,
                     out_path: Path, speed: float = 1.0,
                     permitir_voz_gratis: bool = False) -> tuple[Path, dict]:
    """Sintetiza la voz Y devuelve (mp3, alignment) con el timing de cada carácter.
    alignment = {characters, character_start_times_seconds, character_end_times_seconds}.

    speed: multiplicador de velocidad (1.0 = normal, 2.0 = el doble de rápido). Lo que
    la API no cubre (tope 1.2) se completa acelerando el mp3 con ffmpeg, y los tiempos
    se reescalan igual para que los subtítulos sigan sincronizados.

    permitir_voz_gratis: solo para el ÚLTIMO intento de toda la cascada. Con False —lo
    normal— una cuenta que no puede con la voz pedida lanza VozNoDisponible para que se
    pruebe la siguiente."""
    import base64
    nativa, resto = partir_velocidad(speed)
    voice_id = resolve_voice_id(api_key, voice)
    log.info("ElevenLabs: generando voz + timestamps (%d chars, voz=%s, velocidad=%.2fx)…",
             len(text), voice, speed)
    r = _tts_timestamps(voice_id, text, model, api_key, nativa)
    if r.status_code == 402 and voice_id != FREE_FALLBACK_VOICE:
        if not permitir_voz_gratis:
            raise VozNoDisponible(
                f"esta cuenta no puede usar '{voice}' (plan free y voz de biblioteca)")
        log.warning("ÚLTIMO recurso: ninguna cuenta pudo con '%s' -> voz gratis (Antoni).", voice)
        r = _tts_timestamps(FREE_FALLBACK_VOICE, text, model, api_key, nativa)
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs TTS(timestamps) falló [{r.status_code}]: {r.text[:300]}")
    d = r.json()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(d["audio_base64"]))
    alignment = d.get("alignment") or {}
    if abs(resto - 1.0) >= 0.01:
        rapido = acelerar_audio(out_path, resto, out_path.with_name("voz_rapida.mp3"))
        if rapido != out_path:
            out_path.write_bytes(rapido.read_bytes())
            rapido.unlink(missing_ok=True)
            alignment = escalar_alignment(alignment, resto)
            log.info("Voz acelerada a %.2fx (API %.2f + ffmpeg %.2f).", speed, nativa, resto)
    log.info("Voz guardada -> %s (%.0f KB) + alignment", out_path.name,
             out_path.stat().st_size / 1e3)
    return out_path, alignment


def transcribe_words(audio_path: Path, api_key: str) -> list[tuple[str, float, float]]:
    """Transcribe un audio YA GRABADO (no sintetizado acá) y devuelve
    [(palabra, inicio, fin), ...] con el mismo formato que espera
    subtitles._agrupar(). Para cuando hay una voz elegida a mano (un guion
    grabado aparte) y hace falta igual el timing exacto para los subtítulos."""
    with open(audio_path, "rb") as f:
        r = requests.post(
            f"{API}/speech-to-text", headers={"xi-api-key": api_key},
            data={"model_id": "scribe_v1"},
            files={"file": (audio_path.name, f, "audio/mpeg")}, timeout=180,
        )
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs Speech-to-Text falló [{r.status_code}]: {r.text[:300]}")
    palabras = []
    for w in r.json().get("words") or []:
        if w.get("type") == "word" and w.get("text", "").strip():
            palabras.append((w["text"], float(w["start"]), float(w["end"])))
    return palabras


def synthesize(text: str, api_key: str, voice: str, model: str, out_path: Path) -> Path:
    voice_id = resolve_voice_id(api_key, voice)
    log.info("ElevenLabs: generando voz (%d chars, voz=%s, modelo=%s)…",
             len(text), voice, model)
    r = _tts(voice_id, text, model, api_key)

    # Respaldo: si la voz elegida requiere plan pago (voz de biblioteca en plan free),
    # usamos una voz premade gratis para no romper la corrida.
    if r.status_code == 402 and voice_id != FREE_FALLBACK_VOICE:
        log.warning("La voz '%s' requiere plan pago de ElevenLabs (402 paid_plan_required). "
                    "Uso voz gratis de respaldo (Antoni). Para usar tu voz, hacé upgrade "
                    "del plan de ElevenLabs.", voice)
        r = _tts(FREE_FALLBACK_VOICE, text, model, api_key)

    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs TTS falló [{r.status_code}]: {r.text[:300]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    log.info("Voz guardada -> %s (%.0f KB)", out_path.name, out_path.stat().st_size / 1e3)
    return out_path
