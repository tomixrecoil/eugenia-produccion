"""Descarga de un TikTok concreto con yt-dlp (mp4, sin marca de agua cuando es posible)."""
from __future__ import annotations

import time
from pathlib import Path

import yt_dlp

from src.logging_setup import get_logger

log = get_logger()


def download_video(url: str, out_dir: Path, intentos: int = 4) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        # Preferimos un mp4 combinado y vertical apto para reels.
        "format": "mp4/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "overwrites": True,
    }
    log.info("Descargando %s …", url)
    # TikTok tira 403/challenge de forma INTERMITENTE (un momento falla, al siguiente
    # anda). Sin reintento, la ruta autónoma se saltearía el ganador por un bloqueo
    # transitorio. Reintentamos con backoff ante errores que suelen ser pasajeros.
    ultimo = None
    for intento in range(1, intentos + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info))
            # yt-dlp pudo remuxar a .mp4 aunque prepare_filename diga otra cosa.
            if not path.exists():
                mp4 = path.with_suffix(".mp4")
                if mp4.exists():
                    path = mp4
            if not path.exists():
                raise FileNotFoundError(f"La descarga no produjo archivo: {path}")
            log.info("Descargado -> %s (%.1f MB)", path.name, path.stat().st_size / 1e6)
            return path
        except Exception as e:  # noqa: BLE001
            ultimo = e
            msg = str(e)
            # Comparación en MINÚSCULAS: antes se buscaba "Unable to download" con
            # mayúscula y el mensaje real venía "unable to download video data", así
            # que el reintento nunca se activaba. Se agregaron 499/500/502/503/504 y
            # "first byte timeout", que es lo que devuelve TikTok cuando se satura.
            low = msg.lower()
            transitorio = any(t in low for t in (
                "403", "forbidden", "challenge", "unable to download",
                "499", "500", "502", "503", "504", "first byte", "read timed out",
                "timed out", "timeout", "temporary", "connection", "10054",
                "reset by peer", "incomplete read"))
            if intento < intentos and transitorio:
                espera = 3 * intento
                log.warning("Descarga falló (intento %d/%d, transitorio): %s — reintento en %ds…",
                            intento, intentos, msg[:80], espera)
                time.sleep(espera)
                continue
            raise
    raise ultimo  # pragma: no cover
