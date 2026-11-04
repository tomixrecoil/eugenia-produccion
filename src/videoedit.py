"""
Edición de video con ffmpeg:
  - replace_audio: reemplaza el audio original por la voz doblada (mutea el original).
  - overlay_last_secs: superpone el mockup del producto en los últimos N segundos.
  - probe_*: duración / dimensiones / si tiene audio.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.logging_setup import get_logger

log = get_logger()


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{' '.join(cmd)}\n{proc.stderr[-800:]}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def probe_dimensions(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        w, h = out.split(",")[:2]
        return int(w), int(h)
    except (ValueError, IndexError):
        return 1080, 1920


def has_audio(path: Path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return bool(out)


def replace_audio(video: Path, audio: Path, out: Path) -> Path:
    """Reemplaza el audio del video por 'audio' (voz doblada). El video conserva
    su duración; si la voz es más corta, se rellena con silencio."""
    dur = probe_duration(video)
    _run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-filter_complex", "[1:a]apad[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{dur:.3f}", str(out),
    ])
    log.info("Audio reemplazado -> %s", out.name)
    return out


def extend_to_duration(video: Path, target_secs: float, out: Path) -> Path:
    """Alarga el video hasta target_secs congelando el último cuadro. Sirve cuando
    la voz doblada es más larga que el video: sin esto la voz (y el CTA final) se
    cortan. El cuadro congelado del final cae justo donde se muestra el mockup."""
    dur = probe_duration(video)
    delta = max(0.0, target_secs - dur)
    if delta < 0.2:
        return video
    # EL AUDIO SE CONSERVA. Antes iba con -an y salía un video MUDO. Eso rompía en
    # cascada al paso siguiente: mix_voice_over() ve que no hay audio que conservar y
    # cae a replace_audio(), así que el ambiente ASMR del video desaparecía. Pasaba
    # SOLO cuando la voz era más larga que el video, que es justo cuando esta función
    # se usa — por eso era intermitente y difícil de ver.
    # apad rellena el audio con silencio los mismos segundos que dura el cuadro
    # congelado, para que las dos pistas terminen juntas.
    if has_audio(video):
        _run([
            "ffmpeg", "-y", "-i", str(video),
            "-vf", f"tpad=stop_mode=clone:stop_duration={delta:.3f}",
            "-af", f"apad=pad_dur={delta:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", str(out),
        ])
    else:
        _run([
            "ffmpeg", "-y", "-i", str(video),
            "-vf", f"tpad=stop_mode=clone:stop_duration={delta:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-an", str(out),
        ])
    log.info("Video extendido +%.1fs (congela último cuadro, audio %s) -> %s",
             delta, "conservado" if has_audio(video) else "no había", out.name)
    return out


def trim_to_duration(video: Path, target_secs: float, out: Path) -> Path:
    """Recorta el video a target_secs. Necesario cuando la voz es MÁS CORTA que el
    video (pasa al acelerar la voz): sin esto el reel termina con segundos de
    silencio absoluto, que es lo peor que puede pasar en un reel."""
    dur = probe_duration(video)
    if dur - target_secs < 1.0:      # diferencia despreciable, no vale recodificar
        return video
    _run([
        "ffmpeg", "-y", "-i", str(video), "-t", f"{target_secs:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-an", str(out),
    ])
    log.info("Video recortado %.1fs -> %.1fs (la voz terminaba antes) -> %s",
             dur, target_secs, out.name)
    return out


def mix_voice_over(video: Path, voice: Path, out: Path, ambient_vol: float = 0.8) -> Path:
    """Pone la voz ENCIMA del audio ambiente del video (no lo reemplaza). Baja el
    ambiente a 'ambient_vol' y superpone la voz. Para videos sin diálogo donde hay
    que agregar voz en español conservando el sonido de fondo."""
    if not has_audio(video):
        # No hay ambiente que conservar: equivale a poner la voz sola.
        return replace_audio(video, voice, out)
    # La voz que llega acá YA salió normalizada (dynaudnorm+loudnorm antes de esta
    # función). Un SEGUNDO dynaudnorm sobre la mezcla es el que hacía que el volumen
    # subiera al principio y bajara al final: es un filtro ADAPTATIVO, tarda unos
    # cuadros en converger a su ventana de análisis, y ese "converger" se escucha como
    # una rampa. alimiter es instantáneo (solo evita que el pico de la suma se pase de
    # 1.0) — protege contra clipping sin re-normalizar de nuevo toda la pista.
    filt = (f"[0:a]volume={ambient_vol}[amb];"
            f"[1:a]volume=1.0[vo];"
            f"[amb][vo]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[a]")
    _run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(voice),
        "-filter_complex", filt, "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-shortest", str(out),
    ])
    log.info("Voz mezclada sobre el ambiente -> %s", out.name)
    return out


def overlay_logo(video: Path, logo: Path, out: Path, scale: float = 0.35,
                 position: str = "top", margin: int = 40) -> Path:
    """Pega el logo de la marca durante TODO el video (marca de agua).
    scale = ancho del logo como fracción del ancho del video (0.35 = 35%).
    position: top | top-left | top-right | bottom."""
    if not logo or not Path(logo).exists():
        log.warning("No hay logo (%s) -> el video sale sin marca.", logo)
        return video
    w, h = probe_dimensions(video)
    target_w = max(1, int(w * scale))
    x = {"top": "(W-w)/2", "top-left": str(margin), "top-right": "W-w-%d" % margin,
         "bottom": "(W-w)/2"}.get(position, "(W-w)/2")
    y = f"H-h-{margin}" if position == "bottom" else str(margin)
    filt = f"[1:v]scale={target_w}:-1[lg];[0:v][lg]overlay={x}:{y}"
    audio_args = ["-c:a", "copy"] if has_audio(video) else []
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-i", str(logo),
         "-filter_complex", filt, *audio_args, str(out)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        # Un fallo del logo no debe frenar la publicación del reel.
        log.warning("No pude pegar el logo (%s) -> sigo sin él.", (proc.stderr or "")[-200:])
        return video
    log.info("Logo superpuesto (%s, %.0f%% del ancho) -> %s", position, scale * 100, Path(out).name)
    return Path(out)


def burn_subtitles(video: Path, ass_file: Path, out: Path) -> Path:
    """Quema los subtítulos (.ass) EN el video. Tienen que ir quemados: Instagram,
    Facebook y TikTok no muestran archivos de subtítulos aparte.
    El filtro 'subtitles' de ffmpeg no traga rutas de Windows (C:\\...), así que se
    ejecuta con el cwd en la carpeta del .ass y se lo nombra por archivo."""
    if not ass_file or not Path(ass_file).exists():
        log.warning("No hay archivo de subtítulos -> publico sin subtítulos.")
        return video
    ass_file = Path(ass_file).resolve()
    # Fuentes propias (30/08): sin admin en esta PC no se pueden instalar fuentes a
    # nivel sistema, y una instalada solo "por usuario" no la ve libass/directwrite
    # (probado: cae a Arial en silencio). fontsdir se lo pasa directo al filtro, sin
    # depender de que Windows la tenga "instalada" — portátil y confirmado que anda.
    # RELATIVA a la carpeta del .ass (que es el cwd de este subprocess): una ruta
    # absoluta con la letra de unidad ("C:...") rompe el parser del filtro de ffmpeg,
    # que usa ":" como separador de opciones (probado, tira "Error parsing a filter
    # description"). Sin ese problema porque nunca lleva dos puntos.
    fuentes_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    fontsdir = ""
    if fuentes_dir.is_dir():
        rel = os.path.relpath(fuentes_dir, start=ass_file.parent).replace("\\", "/")
        fontsdir = f":fontsdir={rel}"
    cmd = [
        "ffmpeg", "-y", "-i", str(Path(video).resolve()),
        "-vf", f"subtitles={ass_file.name}{fontsdir}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy", str(Path(out).resolve()),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ass_file.parent))
    if proc.returncode != 0:
        # Un fallo de subtítulos NO debe frenar la publicación del reel.
        log.warning("No pude quemar los subtítulos (%s) -> sigo sin ellos.",
                    (proc.stderr or "")[-200:])
        return video
    log.info("Subtítulos quemados -> %s", Path(out).name)
    return Path(out)


def normalize_for_publish(video: Path, out: Path) -> Path:
    """Re-codifica a specs seguras para Instagram/Facebook Reels:
    H.264 High yuv420p + AAC 48kHz estéreo + moov al inicio (faststart)."""
    _run([
        "ffmpeg", "-y", "-i", str(video),
        "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
        "-movflags", "+faststart", str(out),
    ])
    log.info("Video normalizado para publicar -> %s", out.name)
    return out


def overlay_last_secs(video: Path, image: Path, secs: int, out: Path,
                      scale: float = 0.5, position: str = "bottom",
                      ancho_px: int | None = None, y_px: int | None = None) -> Path:
    """Superpone 'image' (mockup) en los últimos 'secs' segundos.
    ancho_px / y_px (opcionales): tamaño y altura exactos en píxeles, para ubicarlo en
    el espacio libre entre el logo y los subtítulos. Sin ellos, como siempre."""
    dur = probe_duration(video)
    w, _h = probe_dimensions(video)
    # TOPE: el mockup nunca puede comerse el reel entero. Con un video corto (pasó
    # con uno de 10,6s y un mockup de 12s) el producto aparecía desde el segundo 0:
    # sin gancho, sin video, un cartel fijo. Se limita al 45% de la duración, con
    # un piso de 3s para que igual se llegue a leer.
    tope = max(3.0, dur * 0.45)
    if secs > tope:
        log.info("Mockup de %ds sobre un video de %.1fs taparía casi todo -> lo bajo a %.1fs.",
                 secs, dur, tope)
        secs = tope
    start = max(0.0, dur - secs)
    target_w = max(1, int(ancho_px)) if ancho_px else max(1, int(w * scale))

    ypos = {"bottom": "H-h-60", "center": "(H-h)/2", "top": "60",
            "center-alto": "(H-h)/2-120"}.get(position, "H-h-60")
    if y_px is not None:
        ypos = str(int(y_px))
    filt = (
        f"[1:v]scale={target_w}:-1[mk];"
        f"[0:v][mk]overlay=(W-w)/2:{ypos}:enable='gte(t,{start:.3f})'"
    )
    audio_args = ["-c:a", "copy"] if has_audio(video) else []
    _run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(image),
        "-filter_complex", filt, *audio_args, str(out),
    ])
    log.info("Mockup superpuesto (últimos %.1fs) -> %s", secs, out.name)
    return out
