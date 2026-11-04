#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Registro de qué video FUENTE se usó en cada reel, con la regla de repetición.

Por qué existe
--------------
El pipeline automático ya evita duplicados: guarda el reel con el ID del video de
TikTok como clave y `find_winners` saltea los que están en `processed_ids`. Pero los
reels armados a mano se guardaron con nombres propios ("bonsai-arte", "agro-mix"), así
que su video fuente quedó SIN registrar: el pipeline puede volver a elegirlo y publicar
dos veces lo mismo.

La regla (definida por Tomix)
-----------------------------
· ASMR  -> se PUEDE repetir infinitas veces: no tiene guion propio, cada pasada lleva un
           guion y un ángulo distintos. Solo se registra el uso para no repetir el ÁNGULO.
· TRADUCIR / ya en español -> NO se repite: el contenido hablado es fijo. Se bloquea
           marcándolo como procesado, que es lo que mira el pipeline. Lo único que puede
           variar en un traducido es la voz y el copy, y eso no justifica republicarlo.

Uso:
    python registro_fuentes.py --listar
    python registro_fuentes.py --registrar bonsai bonsai-arte 7478146540746427703
    python registro_fuentes.py --backfill      # carga los reels ya hechos a mano
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src import state  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()
REGISTRO = ROOT / "state" / "fuentes_usadas.json"
CARPETA = {"bonsai": Path(r"C:/Users/Tomix/Desktop/S e r v i c i o s/Bonsai/@Bonsais"),
           "hidroponia": Path(r"C:/Users/Tomix/Desktop/S e r v i c i o s/Hydropony/@Agrotonomy")}


# La FUENTE DE VERDAD es R2, no el disco: la PC puede estar apagada y Eugenia tiene que
# poder consultar el registro igual desde WhatsApp. El archivo local queda solo como
# copia de trabajo por si R2 no responde.
R2_KEY = "marketing-reels/fuentes/usadas.json"
WORKER = ROOT / "cloudflare-worker"


def _r2_leer() -> dict | None:
    import subprocess
    import r2io
    if r2io.en_nube():
        return r2io.get_json(R2_KEY)
    try:
        p = subprocess.run(["npx", "wrangler", "r2", "object", "get", R2_KEY, "--remote", "--pipe"],
                           cwd=WORKER, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120, shell=True)
        if p.returncode == 0 and p.stdout.strip():
            return json.loads(p.stdout)
    except Exception as e:  # noqa: BLE001
        log.warning("R2 no respondió (%s); uso la copia local.", str(e)[:70])
    return None


def _r2_escribir(d: dict) -> bool:
    import subprocess, tempfile
    import r2io
    if r2io.en_nube():
        return r2io.put_json(R2_KEY, d)
    tmp = Path(tempfile.gettempdir()) / "fuentes_usadas.json"
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        p = subprocess.run(["npx", "wrangler", "r2", "object", "put", R2_KEY, "--file", str(tmp),
                            "--content-type", "application/json", "--remote"],
                           cwd=WORKER, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180, shell=True)
        return p.returncode == 0
    except Exception as e:  # noqa: BLE001
        log.warning("No pude escribir en R2 (%s).", str(e)[:70])
        return False


def _leer() -> dict:
    remoto = _r2_leer()
    if remoto is not None:
        return remoto
    if REGISTRO.is_file():
        try:
            return json.loads(REGISTRO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _guardar(d: dict) -> None:
    # Primero R2 (la fuente de verdad), después la copia local.
    ok = _r2_escribir(d)
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    if not ok:
        log.warning("Quedó guardado SOLO en disco: sincronizar a R2 cuando vuelva.")


def _ubicar(nicho: str, tiktok_id: str) -> tuple[str, Path | None]:
    """Devuelve (clase, archivo) leyendo dónde está guardado el video hoy."""
    # En la nube las fuentes se bajan de R2 a FUENTES_DIR/<nicho>/<clase>/... (misma forma).
    import os
    base = Path(os.environ["FUENTES_DIR"]) / nicho if os.getenv("FUENTES_DIR") else CARPETA.get(nicho)
    if not base or not base.is_dir():
        return "?", None
    for clase in ("ASMR", "TRADUCIR"):
        for mp4 in (base / clase).rglob(f"*{tiktok_id}*.mp4"):
            return clase, mp4
    return "?", None


def clase_de(nicho: str, tiktok_id: str) -> str:
    """ASMR o TRADUCIR, leyendo dónde está guardado el archivo hoy."""
    return _ubicar(nicho, tiktok_id)[0]


def huella(mp4: Path) -> str:
    """MD5 del archivo. Sirve para lo que el ID de TikTok NO detecta: el MISMO video
    bajado dos veces con IDs distintos (repost de la cuenta, o el mismo clip en dos
    perfiles). Sin esto se publicaría dos veces el mismo video creyendo que son dos
    fuentes distintas — ya hay 3 pares así en la carpeta de bonsái."""
    import hashlib
    try:
        return hashlib.md5(mp4.read_bytes()).hexdigest()
    except OSError:
        return ""


def registrar(nicho: str, reel: str, tiktok_id: str, angulo: str = "") -> dict:
    """Anota el uso. Si la fuente es TRADUCIR, además la BLOQUEA para el pipeline."""
    reg = _leer()
    clase, mp4 = _ubicar(nicho, tiktok_id)
    key = f"{nicho}:{tiktok_id}"
    usos = reg.get(key, {}).get("usos", [])
    usos.append({"reel": reel, "fecha": datetime.now().strftime("%Y-%m-%d"), "angulo": angulo})
    reg[key] = {"nicho": nicho, "tiktok_id": tiktok_id, "clase": clase, "usos": usos,
                "md5": reg.get(key, {}).get("md5") or (huella(mp4) if mp4 else "")}
    _guardar(reg)

    bloqueado = False
    if clase == "TRADUCIR":
        # El pipeline saltea lo que está en processed_ids. Se registra el ID DE TIKTOK
        # (no el nombre del reel) porque es lo que mira find_winners.
        prev = state.load_processed(nicho).get(tiktok_id) or {}
        prev.update({"usado_en": reel, "bloqueado_por": "registro_fuentes (TRADUCIR: contenido fijo)",
                     "processed_at": datetime.now().isoformat(timespec="seconds")})
        state.mark_processed(nicho, tiktok_id, prev)
        bloqueado = True
    return {"clase": clase, "usos": len(usos), "bloqueado": bloqueado}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--registrar", nargs=3, metavar=("NICHO", "REEL", "TIKTOK_ID"))
    ap.add_argument("--angulo", default="")
    ap.add_argument("--backfill", action="store_true")
    a = ap.parse_args()

    if a.registrar:
        nicho, reel, tid = a.registrar
        r = registrar(nicho, reel, tid, a.angulo)
        log.info("%s (%s) -> clase=%s usos=%d %s", tid, reel, r["clase"], r["usos"],
                 "BLOQUEADO para el pipeline" if r["bloqueado"] else "(ASMR: se puede repetir)")
        return 0

    if a.backfill:
        # Los reels armados a mano en esta sesión, con su video fuente real.
        HECHOS = [
            ("hidroponia", "agro-mix", "7214104886084898054", "decenas de verduras sin tierra"),
            ("hidroponia", "agro-lechuga", "7507576587345235222", "de una semilla a una cosecha"),
            ("hidroponia", "agro-cosecha", "7337993334679555360", "qué químicos le das a tu familia"),
            ("hidroponia", "agro-depto", "7497186398642900246", "vives en departamento"),
            ("hidroponia", "agro-repollo", "7584406548030459158", "vegetales gigantes en 1 m2"),
            ("hidroponia", "agro-perejil", "7587027748355394838", "hierbas infinitas"),
            ("hidroponia", "agro-albahaca", "7458251204871703841", "albahaca todo el año"),
            ("hidroponia", "agro-semilla", "7524646307978398998", "de una semilla a tu comida"),
            ("hidroponia", "hidro-torres", "7472710077875522838", "torres verticales abundancia"),
            ("hidroponia", "hidro-mesa", "7014888718301465861", "de tu balcón a tu mesa"),
            ("bonsai", "bonsai-arte", "7478146540746427703", "miedo a que se muera"),
            ("bonsai", "bonsai-sauce", "7335077034437152032", "dos personas, mismo arbolito"),
            ("bonsai", "bonsai-dosmanos", "7350386923803856161", "dos personas, mismo vivero"),
            ("bonsai", "bonsai-dosriegos", "7475014591580310789", "dos riegos, uno se muere"),
        ]
        blo = rep = 0
        for nicho, reel, tid, ang in HECHOS:
            r = registrar(nicho, reel, tid, ang)
            if r["bloqueado"]:
                blo += 1
            else:
                rep += 1
            log.info("  %-16s %s -> %-8s %s", reel, tid, r["clase"],
                     "BLOQUEADO" if r["bloqueado"] else "repetible")
        log.info("Backfill listo: %d bloqueados (TRADUCIR) · %d repetibles (ASMR)", blo, rep)
        return 0

    reg = _leer()
    if not reg:
        log.info("Registro vacío.")
        return 0
    for key, d in sorted(reg.items()):
        log.info("%-14s %-10s usos=%d  %s", d["nicho"], d["clase"], len(d["usos"]),
                 ", ".join(u["reel"] for u in d["usos"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
