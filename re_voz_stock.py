#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Re-dobla los reels del stock que quedaron con el guion de la fórmula ("Imagina...").

Qué reusa y qué rehace
----------------------
El video fuente (elegido, verificado y registrado) se REUSA: no se toca el registro de
fuentes ni se gasta en re-clasificar nada. Se rehace solo lo barato o gratis:
  guion  -> camino oficial del pipeline (Gemini mira el video; prompts/ ya sin fórmula)
  voz    -> misma cascada de siempre: Antonio (las 5 cuentas ElevenLabs) -> Charon.
            Sin nada disponible -> para y sigue otro día.
  render -> ffmpeg local.
El reel re-hecho PISA el mismo id y la misma URL en R2, y queda marcado arreglado=True.
Eugenia solo publica del stock los arreglados.

Uso:
    python re_voz_stock.py            # todos los pendientes hasta quedarse sin cuota
    python re_voz_stock.py --uno      # uno solo (para ver cómo queda)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import armar_stock  # noqa: E402
import producir_stock as ps  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()


def pendientes() -> list[dict]:
    return [x for x in armar_stock.leer_index() if not x.get("arreglado")]


def _fuente_de(item: dict) -> Path | None:
    """El video fuente a partir del id del reel (stk-<nicho5>-<últimos 6 del TikTok id))."""
    last6 = item["id"].rsplit("-", 1)[-1]
    base = ps.CARPETA.get(item["nicho"])
    if not base:
        return None
    hits = [p for p in (base / "ASMR").rglob(f"*{last6}.mp4")]
    return hits[0] if len(hits) == 1 else None


def rehacer(item: dict) -> str:
    """Re-dobla UN reel. Devuelve la voz usada. Levanta CuotaAgotada si Charon no puede."""
    nicho, clave = item["nicho"], item["id"]
    mp4 = _fuente_de(item)
    if not mp4:
        raise FileNotFoundError(f"no encontré la fuente única de {clave}")
    niche = config.load_niche(nicho)
    out = ROOT / "output" / nicho / clave
    guion = ps.guion_del_pipeline(nicho, niche, clave, mp4, out)
    # Cascada completa Charon -> Antonio (las dos gratis, se resetean solas). Lo único
    # vetado acá es Antoni: un re-doblaje puede esperar la recarga, una voz que no es
    # de la marca no se arregla más.
    final, usada = ps.renderizar_reel(nicho, clave, mp4, guion, niche,
                                      sin_voz_no_marca=True)
    # Mismo id -> reemplaza la fila y pisa reels/<id>.mp4 en R2 (misma URL). El copy y el
    # título existentes se conservan; NO se vuelve a registrar la fuente (ya está).
    armar_stock.agregar(nicho, clave, final, item.get("copy", ""),
                        item.get("titulo", clave), voz=usada, guion=guion,
                        tipo=item.get("tipo", "guion_nuevo_asmr"),
                        extras={"arreglado": True})
    return usada


def correr(maximo: int = 999) -> tuple[int, int, bool]:
    """(arreglados, restantes, corto_por_cuota). Comparte el candado del productor."""
    config.read_env()
    if not ps._tomar_lock():
        log.info("Otro productor está corriendo; no me meto.")
        return 0, len(pendientes()), False
    hechos, cuota = 0, False
    try:
        cola = pendientes()
        log.info("Re-doblaje: %d reels con guion viejo.", len(cola))
        for item in cola[:maximo]:
            try:
                ps.latido("redoblaje", corriendo=True, video_actual=item["id"],
                          pendientes=len(cola) - hechos)
                usada = rehacer(item)
                hechos += 1
                log.info("Re-hecho %s con %s (%d/%d)", item["id"], usada, hechos, len(cola))
            except ps.CuotaAgotada as e:
                log.warning("Sin cuota de Charon (%s): sigo otro día. Nada se rompió.", e)
                cuota = True
                break
            except Exception as e:  # noqa: BLE001
                if ps._es_cuota(e):
                    log.warning("Cuota agotada (%s): paro por hoy.", str(e)[:80])
                    cuota = True
                    break
                log.warning("Falló %s (%s): sigo con el próximo.", item["id"], str(e)[:100])
    finally:
        ps._soltar_lock()
        ps.latido("redoblaje", corriendo=False, pendientes=len(pendientes()))
    return hechos, len(pendientes()), cuota


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uno", action="store_true", help="re-dobla uno solo, para verlo")
    a = ap.parse_args()
    hechos, restan, cuota = correr(1 if a.uno else 999)
    log.info("Re-doblados: %d | pendientes: %d%s", hechos, restan,
             " | corté por cuota (mañana sigue solo)" if cuota else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
