"""
Descubrimiento de TikToks "ganadores" de un perfil usando yt-dlp.

Estrategia:
  1. Listar el perfil en modo flat (rápido) -> IDs + URLs.
  2. Extraer metadata completa de los N más recientes -> view_count / likes.
  3. Filtrar los ya procesados, aplicar piso de vistas, ordenar por vistas
     y devolver los top_k ganadores.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from src.logging_setup import get_logger

log = get_logger()


@dataclass
class VideoMeta:
    id: str
    url: str
    title: str
    view_count: int
    like_count: int
    # De qué perfil salió. Hace falta para el modo "un video por cada slot encendido"
    # y para que la interfaz pueda decir de dónde vino cada ganador.
    fuente: str = ""
    # Si viene de una carpeta local (no de TikTok/YouTube), la ruta del archivo en
    # disco. Con esto seteado, process_video no descarga nada.
    local_path: str = ""

    @property
    def engagement(self) -> float:
        if not self.view_count:
            return 0.0
        return self.like_count / self.view_count


# Cache de channel_id por perfil. La URL "https://tiktok.com/@usuario" falla seguido
# con "Unable to extract secondary user ID"; la forma "tiktokuser:<channel_id>" es
# MUCHO más estable (medido: 3/3 vs fallos constantes). Se guarda el id la primera
# vez que se resuelve y después se usa siempre esa vía.
_CACHE_CANALES = Path(__file__).resolve().parent.parent / "state" / "tiktok_channels.json"

# Cookies de una sesión de TikTok, en formato Netscape (cookies.txt).
#
# Desde el 21/08/2026 TikTok NO deja LISTAR un perfil sin sesión: devuelve una página
# vacía de ~1,4 KB y yt-dlp corta con "Unable to extract secondary user ID". Falla igual
# por la URL del perfil que por la vía tiktokuser:<channel_id>, así que el cache de
# arriba tampoco lo salva. Los videos SUELTOS sí se leen: lo bloqueado es el listado.
#
# Con este archivo presente el escaneo vuelve a andar. Se exporta una sola vez desde el
# navegador donde haya sesión de TikTok (extensión "Get cookies.txt LOCALLY") y se
# guarda como state/tiktok_cookies.txt. No se leen del navegador en caliente porque
# Chrome 127+ cifra las cookies con DPAPI y yt-dlp no puede descifrarlas.
_COOKIES = Path(__file__).resolve().parent.parent / "state" / "tiktok_cookies.txt"


def _con_cookies(opts: dict) -> dict:
    """Le suma las cookies a las opciones de yt-dlp, si el archivo está."""
    if _COOKIES.is_file():
        opts = dict(opts)
        opts["cookiefile"] = str(_COOKIES)
    return opts


def _cache_leer() -> dict:
    try:
        return json.loads(_CACHE_CANALES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cache_guardar(perfil: str, channel_id: str) -> None:
    try:
        d = _cache_leer()
        d[perfil] = channel_id
        _CACHE_CANALES.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_CANALES.write_text(json.dumps(d, indent=1), encoding="utf-8")
    except Exception:
        pass


def _resolver_channel_id(profile_url: str, entradas: list[dict]) -> str | None:
    """Saca el channel_id mirando la metadata de uno de los videos del perfil."""
    for e in entradas[:3]:
        url = e.get("url") or e.get("webpage_url")
        if not url:
            continue
        try:
            with yt_dlp.YoutubeDL(_con_cookies({"quiet": True, "no_warnings": True,
                                                "skip_download": True})) as ydl:
                info = ydl.extract_info(url, download=False)
            cid = info.get("channel_id")
            if cid:
                _cache_guardar(profile_url, cid)
                log.info("channel_id de %s guardado (escaneos más estables).", profile_url)
                return cid
        except Exception:
            continue
    return None


def _flat_entries(profile_url: str, scan_count: int, intentos: int = 4) -> list[dict]:
    """Lista los videos del perfil. TikTok falla de forma INTERMITENTE con
    "Unable to extract secondary user ID", así que: (1) si ya conocemos el channel_id
    se usa la vía estable `tiktokuser:`, (2) si no, se prueba la URL normal con
    reintentos y se aprende el channel_id para las próximas veces."""
    opts = _con_cookies({
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": scan_count,
        "skip_download": True,
    })
    cid = _cache_leer().get(profile_url)
    candidatas = ([f"tiktokuser:{cid}"] if cid else []) + [profile_url]

    ultimo = None
    for intento in range(1, intentos + 1):
        for url in candidatas:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                entradas = info.get("entries", []) or []
                if entradas:
                    if not cid:   # aprender el id para las próximas corridas
                        _resolver_channel_id(profile_url, entradas)
                    return entradas
                ultimo = RuntimeError("el perfil no devolvió entradas")
            except Exception as e:  # noqa: BLE001
                ultimo = e
        if intento < intentos:
            espera = 4 * intento
            log.warning("Escaneo falló (intento %d/%d: %s) — reintento en %ds…",
                        intento, intentos, str(ultimo)[:80], espera)
            time.sleep(espera)
    raise ultimo if ultimo else RuntimeError("no pude escanear el perfil")


def _full_meta(video_url: str) -> VideoMeta | None:
    opts = _con_cookies({"quiet": True, "no_warnings": True, "skip_download": True})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except Exception as e:  # video privado, borrado, geo-bloqueado, etc.
        log.warning("No se pudo leer metadata de %s: %s", video_url, e)
        return None
    return VideoMeta(
        id=str(info.get("id", "")),
        url=info.get("webpage_url", video_url),
        title=(info.get("title") or info.get("description") or "")[:120],
        view_count=int(info.get("view_count") or 0),
        like_count=int(info.get("like_count") or 0),
    )


def find_winners(
    profile_url: str | list[str],
    scan_count: int,
    top_k: int,
    min_views: int,
    processed_ids: set[str],
    uno_por_fuente: bool = False,
) -> list[VideoMeta]:
    """profile_url puede ser UNA url (como siempre) o una LISTA de perfiles.

    Con `uno_por_fuente=False` (lo de siempre) los videos de todos los perfiles caen en
    una sola bolsa y se devuelven los top_k más vistos ENTRE TODOS. Eso hace que un
    perfil chico con videos muy vistos se lleve todos los cupos y los demás no aporten
    nada nunca.

    Con `uno_por_fuente=True` se devuelven los top_k de CADA perfil: es el modo que usa
    el dry run para preparar un video por cada slot encendido. El resto del filtrado
    —ya procesados, repetidos entre perfiles y piso de vistas— es exactamente el mismo
    en los dos modos.

    Si un perfil falla, se sigue con los demás (no se cae la corrida por uno roto).
    """
    perfiles = [profile_url] if isinstance(profile_url, str) else list(profile_url)
    perfiles = [p.strip() for p in perfiles if p and p.strip()]

    entries: list[tuple[str, dict]] = []
    for p in perfiles:
        log.info("Escaneando %s (últimos %d videos)…", p, scan_count)
        try:
            e = _flat_entries(p, scan_count)
            log.info("  devolvió %d entradas.", len(e))
            entries += [(p, x) for x in e]
        except Exception as exc:  # noqa: BLE001
            log.warning("  no pude escanear %s (%s) — sigo con los demás.", p, str(exc)[:90])
    if len(perfiles) > 1:
        log.info("Total de %d perfiles: %d entradas.", len(perfiles), len(entries))

    candidates: list[VideoMeta] = []
    vistos: set[str] = set()
    for perfil, e in entries:
        vid = str(e.get("id", ""))
        if vid and (vid in processed_ids or vid in vistos):
            continue
        if vid:
            vistos.add(vid)   # el mismo video puede venir de dos perfiles
        url = e.get("url") or e.get("webpage_url")
        if not url:
            continue
        # Algunas versiones de yt-dlp ya traen view_count en modo flat.
        if e.get("view_count") is not None:
            meta = VideoMeta(
                id=vid,
                url=url,
                title=(e.get("title") or "")[:120],
                view_count=int(e.get("view_count") or 0),
                like_count=int(e.get("like_count") or 0),
            )
        else:
            meta = _full_meta(url)
        if meta is None:
            continue
        if meta.view_count < min_views:
            continue
        meta.fuente = perfil
        candidates.append(meta)

    candidates.sort(key=lambda m: m.view_count, reverse=True)
    if uno_por_fuente:
        # Ya vienen ordenados por vistas, así que el primero de cada perfil es su mejor.
        por_fuente: dict[str, list[VideoMeta]] = {}
        for c in candidates:
            por_fuente.setdefault(c.fuente, []).append(c)
        winners = []
        for p in perfiles:                       # respeta el orden de los slots
            winners += por_fuente.get(p, [])[:max(1, top_k)]
        for p in perfiles:
            if not por_fuente.get(p):
                log.info("  ⚠ %s no aportó ningún ganador nuevo.", p)
    else:
        winners = candidates[:top_k]

    for w in winners:
        log.info("  🏆 %s | %s vistas | %s", w.id, f"{w.view_count:,}", w.title)
    if not winners:
        log.info("No hay ganadores nuevos que superen %s vistas.", f"{min_views:,}")
    return winners
