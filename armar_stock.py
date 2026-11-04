#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Produce reels y los deja LISTOS en R2 para que Eugenia los publique sin la PC.

Por qué existe
--------------
El Worker de Cloudflare no tiene ffmpeg: no puede armar un video. Por eso "subí un
video" solo encolaba una orden y esperaba a que Tomix prendiera la compu. Con un stock
pre-renderizado en R2 eso se termina: el video ya está hecho, y publicar es una llamada
a la API de Meta que el Worker sí puede hacer solo.

Qué sube a R2
-------------
  reels_stock/<id>.mp4        el video terminado
  stock/index.json            la fila: [{id, nicho, r2_url, copy, titulo, video_key}]

Eugenia lee ese index con *stock* y publica el primero con *publicá uno de bonsái*.

Respeta la regla de repetición (ver registro_fuentes.py): un TRADUCIR no se reusa nunca;
un ASMR sí, con otro ángulo.

Uso:
    python armar_stock.py --nicho bonsai --cantidad 5
    python armar_stock.py --listar
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import r2io  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()
WORKER = ROOT / "cloudflare-worker"
BUCKET = "marketing-reels"
INDEX_KEY = f"{BUCKET}/stock/index.json"
BASE_PUBLICA = "https://marketing-ig-scheduler.goldentimeshift.workers.dev/v"


def r2_get(key: str):
    if r2io.en_nube():
        return r2io.get_json(key)
    p = subprocess.run(["npx", "wrangler", "r2", "object", "get", key, "--remote", "--pipe"],
                       cwd=WORKER, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180, shell=True)
    if p.returncode == 0 and p.stdout.strip():
        try:
            return json.loads(p.stdout)
        except json.JSONDecodeError:
            return None
    return None


def r2_put(local: Path, key: str, ctype: str) -> bool:
    if r2io.en_nube():
        return r2io.put_file(local, key, ctype)
    # ABSOLUTA sí o sí: wrangler corre con cwd=cloudflare-worker, así que una ruta
    # relativa al proyecto no resuelve y el put falla sin decir por qué.
    local = Path(local).resolve()
    p = subprocess.run(["npx", "wrangler", "r2", "object", "put", key, "--file", str(local),
                        "--content-type", ctype, "--remote"],
                       cwd=WORKER, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600, shell=True)
    return p.returncode == 0


def r2_delete(key: str) -> bool:
    if r2io.en_nube():
        return r2io.delete(key)
    p = subprocess.run(["npx", "wrangler", "r2", "object", "delete", key, "--remote"],
                       cwd=WORKER, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180, shell=True)
    return p.returncode == 0


def leer_index() -> list:
    d = r2_get(INDEX_KEY)
    return d if isinstance(d, list) else []


def guardar_index(items: list) -> bool:
    tmp = Path(tempfile.gettempdir()) / "stock_index.json"
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return r2_put(tmp, INDEX_KEY, "application/json")


def agregar(nicho: str, reel_id: str, mp4: Path, copy: str, titulo: str = "",
            voz: str = "", guion: str = "", tipo: str = "",
            extras: dict | None = None) -> dict:
    """Sube UN reel ya renderizado al stock. Si el id ya existía, lo REEMPLAZA
    (mismo video_key -> misma URL): así se re-hace un reel sin duplicar la fila.

    voz / guion / tipo viajan con el reel para que Eugenia pueda informar, al publicarlo,
    con qué voz salió y si el guion es inventado (video mudo) o una traducción.
    extras: campos sueltos para la fila (p.ej. arreglado=True tras el re-doblaje).
    """
    if not mp4.is_file():
        raise FileNotFoundError(mp4)
    # Va DENTRO de reels/ a propósito: la ruta pública /v/ del Worker solo sirve archivos
    # de ese prefijo y con nombre plano. Es un guard de seguridad (si no, se podría pedir
    # wa/clientes.json por esa misma ruta), así que el stock se adapta en vez de aflojarlo.
    video_key = f"reels/{reel_id}.mp4"
    if not r2_put(mp4, f"{BUCKET}/{video_key}", "video/mp4"):
        raise RuntimeError("no pude subir el mp4 a R2")
    item = {"id": reel_id, "nicho": nicho, "video_key": video_key,
            "r2_url": f"{BASE_PUBLICA}/{video_key}", "copy": copy,
            "titulo": titulo or reel_id, "creado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "voz": voz, "guion": guion, "tipo": tipo}
    item.update(extras or {})
    idx = leer_index()
    idx = [x for x in idx if x.get("id") != reel_id] + [item]
    if not guardar_index(idx):
        raise RuntimeError("no pude actualizar el index del stock")
    return item


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--agregar", nargs=4, metavar=("NICHO", "ID", "MP4", "COPY_TXT"),
                    help="sube un reel ya hecho: nicho id ruta_mp4 ruta_del_copy.txt")
    a = ap.parse_args()

    if a.agregar:
        nicho, rid, mp4, copyf = a.agregar
        copy = Path(copyf).read_text(encoding="utf-8") if Path(copyf).is_file() else copyf
        it = agregar(nicho, rid, Path(mp4), copy)
        log.info("Agregado al stock: %s (%s) -> %s", it["id"], it["nicho"], it["r2_url"])
        return 0

    idx = leer_index()
    if not idx:
        log.info("Stock VACÍO.")
        return 0
    por = {}
    for x in idx:
        por[x["nicho"]] = por.get(x["nicho"], 0) + 1
    log.info("Stock: %d reels %s", len(idx), por)
    for x in idx:
        log.info("  %-22s %-10s %s", x["id"], x["nicho"], x.get("creado", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
