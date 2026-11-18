#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sube a YouTube (Shorts) los reels que ya salieron en Facebook/Instagram. Corre en
GitHub, como último paso de la producción diaria (nube/producir.yml).

Por qué existe
--------------
Desde el 01/09 no subía nadie: la subida vivía en la producción vieja de la PC y el
interruptor de YouTube era decoración (Tomix, 02/11/2026; analisis/AJUSTES_DECORACION.md).

Cómo decide
-----------
- Lo publicado sale de `stock/publicados.json` (lo anota el Worker al publicar).
- Solo nichos con el interruptor ▶️ YouTube prendido (`state/toggles.json` → yt). El canal
  es el del nicho (`YT_REFRESH_<NICHO>` en la bóveda) o, si está vacío, el primero conectado
  de ORDEN_CANAL: desde el 18/11 todo va a UN canal (pedido de Tomix). La app de Google es
  `YT_CLIENT_ID` / `YT_CLIENT_SECRET`.
- Lo ya subido queda en `stock/youtube.json` ({"desde", "subidos": {id: video_id}}). La
  primera vez se anota "desde = ahora": no se suben los cientos de reels viejos.
- Máximo MAX_POR_CORRIDA por vez: YouTube da cupo para ~6 subidas por día.

Uso:
    python subir_youtube_nube.py              # lo que falte
    python subir_youtube_nube.py --probar     # dice qué subiría, sin subir
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import r2io  # noqa: E402
print(f"credenciales de la bóveda: {r2io.cargar_credenciales()}")
print(f"ajustes de nicho del panel: {r2io.bajar_nichos(ROOT / 'niches') or 'ninguno (uso la copia)'}")

import os  # noqa: E402

REGISTRO = "stock/youtube.json"
# YouTube da 10.000 unidades por día y cada subida gasta 1.600: entran 6 por día.
MAX_POR_CORRIDA = 6
# Un solo canal para todo (Tomix, 18/11): cada nicho usa SU permiso si está cargado en
# Credenciales (YT_REFRESH_<NICHO>); si está vacío, el primero conectado de esta lista.
# Para mandar todo a un canal, alcanza con conectar ese canal en uno solo de los campos.
ORDEN_CANAL = ("hidroponia", "bonsai", "terrarios", "herbologia")


def _clave(nicho: str) -> str:
    return "YT_REFRESH_" + re.sub(r"[^A-Z0-9]", "_", nicho.upper())


def _clave_canal(nicho: str) -> str:
    """La clave del permiso que usa este nicho: la suya o, si está vacía, la primera
    conectada de ORDEN_CANAL. "" si no hay ningún canal conectado."""
    for n in (nicho, *ORDEN_CANAL):
        if os.getenv(_clave(n)):
            return _clave(n)
    return ""


def _servicio(nicho: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=os.environ[_clave_canal(nicho)],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"],
                        client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _titulo_y_gancho(copy: str) -> tuple[str, str]:
    """El título es la primera línea del copy (el gancho); el gancho de la descripción,
    el primer párrafo. YouTube corta el título en 100."""
    lineas = [l.strip() for l in (copy or "").splitlines() if l.strip()]
    primera = lineas[0] if lineas else "Mira esto"
    titulo = (primera[:88].rstrip() + " #Shorts")[:100]
    gancho = (copy or "").strip().split("\n\n")[0].strip() or primera
    return titulo, gancho


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probar", action="store_true")
    a = ap.parse_args()

    if not (os.getenv("YT_CLIENT_ID") and os.getenv("YT_CLIENT_SECRET")):
        print("Sin app de Google en la bóveda (YT_CLIENT_ID / YT_CLIENT_SECRET): no subo nada.")
        return 0
    toggles = r2io.get_json("state/toggles.json") or {}
    pubs = r2io.get_json("stock/publicados.json") or []
    reg = r2io.get_json(REGISTRO) or {}
    if not reg.get("desde"):
        reg = {"desde": datetime.now(timezone.utc).isoformat(), "subidos": {}}
        if not a.probar:
            r2io.put_json(REGISTRO, reg)
        print(f"Primera vez: subo solo lo publicado desde {reg['desde']}.")
    subidos = reg.setdefault("subidos", {})

    pendientes = []
    for p in pubs:
        n, rid = p.get("nicho") or "", p.get("id") or ""
        if not rid or rid in subidos or str(p.get("ts", "")) < reg["desde"]:
            continue
        if not (toggles.get(n) or {}).get("yt", True):
            continue
        if not _clave_canal(n):
            print(f"  {rid}: no hay ningún canal de YouTube conectado, lo salteo.")
            continue
        pendientes.append(p)
    # Los más nuevos primero: con 6 por día de cupo y 8 publicados, que no se atasque
    # en los viejos (cuyo video ya se había borrado: ver el Worker, 18/11).
    pendientes.sort(key=lambda p: str(p.get("ts", "")), reverse=True)
    print(f"Para subir: {len(pendientes)} (subo hasta {MAX_POR_CORRIDA}).")
    if a.probar or not pendientes:
        for p in pendientes:
            print("  ·", p["id"], p["nicho"], _titulo_y_gancho(p.get("copy", ""))[0])
        return 0

    import config
    import subir_youtube
    servicios: dict = {}
    hechos = 0
    for p in pendientes:
        if hechos >= MAX_POR_CORRIDA:
            break
        n, rid = p["nicho"], p["id"]
        carpeta = Path(tempfile.mkdtemp()) / rid      # el id de la carpeta va al sck del link
        carpeta.mkdir(parents=True)
        video = carpeta / "publicar.mp4"
        if not r2io.bajar(p.get("video_key") or f"reels/{rid}.mp4", video):
            # Ya no existe (el Worker borraba el video al publicar, hasta el 18/11): se
            # anota para no reintentarlo todos los días y trabar a los nuevos.
            print(f"  {rid}: el video ya no está en R2, lo marco y sigo.")
            subidos[rid] = {"yt": None, "sin_video": True, "nicho": n}
            r2io.put_json(REGISTRO, reg)
            continue
        titulo, gancho = _titulo_y_gancho(p.get("copy", ""))
        try:
            tags = list(config.load_niche(n).yt_tags or []) or [n, "Shorts"]
        except Exception:  # noqa: BLE001
            tags = [n, "Shorts"]
        try:
            canal = _clave_canal(n)
            yt = servicios.get(canal) or servicios.setdefault(canal, _servicio(n))
            vid = subir_youtube.publish_short(video, titulo, gancho, tags, yt=yt, nicho=n)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            print(f"  {rid}: YouTube falló: {msg[:200]}")
            if "quota" in msg.lower():
                print("Sin cupo de YouTube por hoy: mañana sigue.")
                break
            continue
        finally:
            video.unlink(missing_ok=True)
        subidos[rid] = {"yt": vid, "nicho": n, "ts": datetime.now(timezone.utc).isoformat()}
        r2io.put_json(REGISTRO, reg)      # después de CADA uno: un corte no lo sube dos veces
        hechos += 1
        print(f"  ✅ {rid} → https://youtube.com/shorts/{vid}")
    print(f"Subidos: {hechos}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
