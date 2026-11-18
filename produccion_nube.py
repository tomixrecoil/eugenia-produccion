#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La producción diaria en la NUBE (GitHub Actions), con la PC apagada.

Una sola pasada, sin dormir: GitHub cobra cada minuto que la máquina está prendida (el
plan gratis trae 2.000 por mes), así que esperar a que Gemini recargue cuota es tirar
minutos. Si hay límite, se corta y mañana sigue.

Cuántos hace: POR_DIA por nicho (uno más de los 2 que se publican), MAX_POR_NICHO si el
nicho tiene poco stock, y lo que un nicho no pudo hacer pasa al siguiente. Nunca más de
lo que falta para tener OBJETIVO reels de ese nicho esperando en el stock.

Uso (lo corre .github/workflows/producir.yml):
    python produccion_nube.py
    python produccion_nube.py --nicho bonsai --cantidad 1     # prueba de uno

Los nichos: los que pasan config.nicho_produce (ver LISTOS abajo).
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
import config  # noqa: E402
import producir_stock  # noqa: E402
from src import toggles  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()

# Los nichos salen de config (14/11/2026): los que están listos para producir
# (config.nicho_produce: fuente, link de venta y nombre de producto cargados), leídos
# DESPUÉS de bajar los ajustes del panel. Antes era ("hidroponia", "bonsai") fijo y un
# nicho nuevo (terrarios, herbología) quedaba afuera aunque estuviera configurado.
# Numerología no entra: su producto sigue en PENDIENTE y ni siquiera se exporta.
LISTOS = tuple(config.nichos_produccion())
# Del reparto automático quedan afuera los que tienen la producción apagada en el panel
# (state/toggles.json; sin entrada = prendido). Así su parte del día va a los demás.
NICHOS = tuple(n for n in LISTOS if toggles.activo(n, "produccion"))
# Se publican 2 por día de cada nicho (6:00 y 18:00 ART). Se producen MÁS (pedido de
# Tomix, 28/10/2026: "siempre más encolados de los que se pueden subir"): la cola crece
# 1 por día y nicho hasta OBJETIVO, y ahí frena sola (también cuida los minutos de GitHub).
POR_DIA = 3
OBJETIVO = 20
# Reparto parejo (02/11/2026): los POR_DIA × nichos del día van primero al nicho con
# MENOS stock, hasta MAX_POR_NICHO cada uno. Antes era 3 fijos por nicho y, como
# hidroponía falla más, quedó con 9 contra 19 de bonsái. El total por día no cambia.
MAX_POR_NICHO = 5
BAJO = 6          # con menos de esto en stock (3 días) produce MAX_POR_NICHO


def repartir(stock: dict[str, int]) -> dict[str, int]:
    """{nicho: cuántos producir hoy}. Cada nicho, POR_DIA (uno más de los 2 que se publican,
    pedido de Tomix 18/11: "tenemos que estar produciendo de más"); el que tiene poco
    stock (menos de BAJO), hasta MAX_POR_NICHO. Nunca más de lo que falta para OBJETIVO.
    Antes se repartían 12 en total al que menos tenía: terrarios y plantas (sin fuentes)
    se llevaban 5 cada uno, hacían 0, y hidroponía y bonsái quedaban con 1 por día
    mientras publicaban 2 (el stock bajaba solo)."""
    plan = {}
    for n, s_ in stock.items():
        quiere = MAX_POR_NICHO if s_ < BAJO else POR_DIA
        plan[n] = max(0, min(quiere, OBJETIVO - s_))
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    # A mano se acepta cualquier nicho listo; si tiene la producción apagada,
    # producir_stock.producir lo dice y no hace nada.
    ap.add_argument("--nicho", choices=LISTOS)
    ap.add_argument("--cantidad", type=int)
    a = ap.parse_args()

    log.info("Nichos listos: %s | en el reparto: %s", list(LISTOS), list(NICHOS))
    idx = armar_stock.leer_index()
    stock = {n: sum(1 for x in idx if x.get("nicho") == n) for n in NICHOS}
    plan = repartir(stock)
    hechos_total, errores_total = [], []
    sobrante = 0
    # El que menos tiene va primero: si se acaba la cuota, que le falte al otro.
    orden = [a.nicho] if a.nicho else sorted(NICHOS, key=lambda n: stock[n])
    for nicho in orden:
        en_stock = stock.get(nicho, 0)
        falta = a.cantidad if a.cantidad else plan.get(nicho, 0)
        # Lo que un nicho anterior no pudo hacer (sin fuentes, Gemini caído) pasa a este,
        # sin pasar de OBJETIVO: el total del día no se pierde.
        if not a.cantidad and sobrante:
            extra = max(0, min(sobrante, OBJETIVO - en_stock - falta))
            falta += extra
            sobrante -= extra
        log.info("%s: %d en stock, produzco %d.", nicho, en_stock, falta)
        if not falta:
            continue
        hechos, errores = producir_stock.producir(nicho, falta)
        sobrante += max(0, falta - len(hechos))
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
