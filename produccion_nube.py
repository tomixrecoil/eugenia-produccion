#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La producción diaria en la NUBE (GitHub Actions), con la PC apagada.

Una sola pasada, sin dormir: GitHub cobra cada minuto que la máquina está prendida (el
plan gratis trae 2.000 por mes), así que esperar a que Gemini recargue cuota es tirar
minutos. Si hay límite, se corta y mañana sigue.

Cuántos hace: los que se publican por día (POR_DIA por nicho), pero nunca más de lo que
falta para tener OBJETIVO reels de ese nicho esperando en el stock.

Uso (lo corre .github/workflows/producir.yml):
    python produccion_nube.py
    python produccion_nube.py --nicho bonsai --cantidad 1     # prueba de uno
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import r2io  # noqa: E402
print(f"credenciales de la bóveda: {r2io.cargar_credenciales()}")   # antes que nada: los módulos de abajo leen las claves
print(f"ajustes de nicho del panel: {r2io.bajar_nichos(ROOT / 'niches') or 'ninguno (uso la copia)'}")

import armar_stock  # noqa: E402
import producir_stock  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()

NICHOS = ("hidroponia", "bonsai")
# Se publican 2 por día de cada nicho (6:00 y 18:00 ART). Se producen MÁS (pedido de
# Tomix, 28/10/2026: "siempre más encolados de los que se pueden subir"): la cola crece
# 1 por día y nicho hasta OBJETIVO, y ahí frena sola (también cuida los minutos de GitHub).
POR_DIA = 3
OBJETIVO = 20
# Reparto parejo (02/11/2026): los POR_DIA × nichos del día van primero al nicho con
# MENOS stock, hasta MAX_POR_NICHO cada uno. Antes era 3 fijos por nicho y, como
# hidroponía falla más, quedó con 9 contra 19 de bonsái. El total por día no cambia.
MAX_POR_NICHO = 5


def repartir(stock: dict[str, int]) -> dict[str, int]:
    """{nicho: cuántos producir hoy}. De a uno, siempre al que menos tiene (contando lo
    ya asignado), sin pasar de OBJETIVO ni de MAX_POR_NICHO."""
    asignado = {n: 0 for n in stock}
    for _ in range(POR_DIA * len(stock)):
        libres = [n for n in stock
                  if asignado[n] < MAX_POR_NICHO and stock[n] + asignado[n] < OBJETIVO]
        if not libres:
            break
        n = min(libres, key=lambda x: (stock[x] + asignado[x], x))
        asignado[n] += 1
    return asignado


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nicho", choices=NICHOS)
    ap.add_argument("--cantidad", type=int)
    a = ap.parse_args()

    idx = armar_stock.leer_index()
    stock = {n: sum(1 for x in idx if x.get("nicho") == n) for n in NICHOS}
    plan = repartir(stock)
    hechos_total, errores_total = [], []
    # El que menos tiene va primero: si se acaba la cuota, que le falte al otro.
    orden = [a.nicho] if a.nicho else sorted(NICHOS, key=lambda n: stock[n])
    for nicho in orden:
        en_stock = stock.get(nicho, 0)
        falta = a.cantidad if a.cantidad else plan.get(nicho, 0)
        log.info("%s: %d en stock, produzco %d.", nicho, en_stock, falta)
        if not falta:
            continue
        hechos, errores = producir_stock.producir(nicho, falta)
        hechos_total += hechos
        errores_total += errores
        if any(e.endswith("CUOTA") for e in errores):
            log.warning("Sin cuota: corto acá, mañana sigue.")
            break
    log.info("Hechos: %d %s", len(hechos_total), hechos_total)
    for e in errores_total:
        log.info("  · %s", e)
    return 0 if hechos_total or not errores_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
