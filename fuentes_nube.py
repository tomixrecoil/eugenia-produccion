#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las fuentes (videos de TikTok) en la NUBE: catalogar lo nuevo y revisar la clase.

Es catalogar_fuente.py + recategorizar_asmr.py sin el escritorio de Tomix: todo vive en
R2 (fuentes_src/ + fuentes_src/manifest.json) y corre en GitHub Actions.

    nuevos   mira los perfiles de TikTok de cada nicho (catalogar_fuente.FUENTES), baja lo
             que no está en R2 (de más vistas a menos, con tope por corrida), lo escucha
             (filtro local + Gemini) y lo sube ya clasificado y verificado ("revisado2").
    revisar  vuelve a escuchar con Gemini las fuentes de R2 que no tienen "revisado2"
             (las que el filtro local dejó sin confirmar) y corrige ASMR/TRADUCIR en el
             manifiesto. El video NO se mueve: cada entrada guarda su "key" en R2.

La clase es lo que manda para producir: ASMR = mudo (guion nuevo), TRADUCIR = habla
(se traduce, o se usa muteado). Un video que nadie pudo escuchar queda sin "revisado2"
y la producción no lo toca: es el mismo seguro que en la PC.

Uso (lo corre .github/workflows/fuentes.yml):
    python fuentes_nube.py nuevos --limite 10
    python fuentes_nube.py revisar --limite 20
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import r2io  # noqa: E402
print(f"credenciales de la bóveda: {r2io.cargar_credenciales()}")   # antes que nada: los módulos de abajo leen las claves
print(f"ajustes de nicho del panel: {r2io.bajar_nichos(ROOT / 'niches') or 'ninguno (uso la copia)'}")

import catalogar_fuente as cf  # noqa: E402
import producir_stock  # noqa: E402
import registro_fuentes  # noqa: E402
import resolver_dudosos as rd  # noqa: E402
from src import audio_voz  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()
MANIFIESTO = producir_stock.MANIFIESTO
DESCARTADOS = "fuentes_src/descartados.json"   # ids que en la PC estaban en dontuse
NICHO_DE = {"agrotonomy": "hidroponia", "bonsai": "bonsai"}
TEMA_DE = {"agrotonomy": "una granja vertical", "bonsai": "bonsáis y jardinería"}
MARCA = "revisado2"


def _tmp() -> Path:
    d = Path(os.getenv("FUENTES_DIR") or tempfile.gettempdir()) / "_catalogo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _nota(clase: str, r: dict) -> str:
    return (f"clasificado : {clase}  [{MARCA}: voz={'si' if r['voz'] else 'no'}, "
            f"idioma={r['idioma']} — {r['que']}]")


def _escuchar(mp4: Path, fuente: str) -> dict | None:
    """Gemini escucha 30 s de audio. None si no se pudo (sin cuota, respuesta ilegible):
    en ese caso el video queda SIN verificar, nunca se adivina."""
    rd.TEMA = TEMA_DE.get(fuente, "jardinería")
    try:
        r = rd.escuchar(mp4, rd._claves())
    except Exception as e:  # noqa: BLE001
        log.warning("No pude escuchar %s (%s).", mp4.name[:40], str(e)[:80])
        return None
    if r.get("idioma") in (None, "", "?"):
        return None
    return r


def nuevos(limite: int) -> int:
    man = r2io.get_json(MANIFIESTO)
    if man is None:
        log.error("No pude leer el manifiesto de R2: no sigo (subiría repetidos).")
        return 1
    conocidos = {e.get("tid") for e in man}
    conocidos |= set(r2io.get_json(DESCARTADOS) or [])
    usados, _ = producir_stock._usados()
    conocidos |= usados

    subidos = 0
    for fuente, f in cf.FUENTES.items():
        nicho = NICHO_DE[fuente]
        vids = [v for v in cf.listar(f["perfiles"]) if v["id"] not in conocidos]
        vids.sort(key=lambda v: -v["vistas"])
        log.info("%s: %d videos nuevos en TikTok (bajo hasta %d).", nicho, len(vids), limite)
        for v in vids[:limite]:
            try:
                from src import download
                crudo = Path(download.download_video(cf._url_video(v), _tmp()))
            except Exception as e:  # noqa: BLE001
                log.warning("No pude bajar %s (%s).", v["id"], str(e)[:80])
                continue
            if not producir_stock._tiene_video(crudo):
                log.warning("%s bajó sin imagen: lo salteo.", v["id"])
                crudo.unlink(missing_ok=True)
                continue
            med = audio_voz.analizar(crudo)
            clase = cf.CLASES.get(med["clase"], "dudosos")
            r = _escuchar(crudo, fuente)
            if r:                                   # Gemini decide; el filtro local orienta
                clase = "TRADUCIR" if r["voz"] else "ASMR"
            elif clase == "dudosos":
                clase = "TRADUCIR"                  # ante la duda, NUNCA como mudo
            tramo = cf.tramo(v["vistas"])
            archivo = f"{cf.tema(v['titulo'], f['vocabulario'])}__{v['id']}.mp4"
            key = f"fuentes_src/{nicho}/{clase}/{tramo}/{archivo}"
            if not r2io.put_file(crudo, key, "video/mp4"):
                log.warning("No pude subir %s a R2.", archivo[:44])
                continue
            txt = cf.ficha(v, clase, med, Path(archivo))
            if r:
                txt = re.sub(r"clasificado :.*", _nota(clase, r), txt, count=1)
            man.append({"nicho": nicho, "clase": clase, "carpeta": tramo, "archivo": archivo,
                        "tid": v["id"], "txt": txt, "md5": registro_fuentes.huella(crudo),
                        "key": key})
            conocidos.add(v["id"])
            crudo.unlink(missing_ok=True)
            subidos += 1
            log.info("+ %s %s %s %s", nicho, clase, tramo, archivo[:50])
            # Se guarda seguido: si GitHub corta la corrida, lo subido no se pierde.
            if subidos % 5 == 0:
                r2io.put_json(MANIFIESTO, man)
    if subidos and not r2io.put_json(MANIFIESTO, man):
        log.error("Subí %d videos pero NO pude guardar el manifiesto.", subidos)
        return 1
    log.info("Nuevos catalogados: %d", subidos)
    return 0


def revisar(limite: int, incluir_usados: bool) -> int:
    man = r2io.get_json(MANIFIESTO)
    if man is None:
        log.error("No pude leer el manifiesto de R2.")
        return 1
    usados, _ = producir_stock._usados()
    pend = [e for e in man if MARCA not in (e.get("txt") or "")
            and (incluir_usados or e.get("tid") not in usados)]
    pend.sort(key=lambda e: producir_stock._peso(e.get("carpeta", "")), reverse=True)
    log.info("Por revisar: %d (tope %d).", len(pend), limite)
    fuente_de = {n: f for f, n in NICHO_DE.items()}
    cambios = 0
    for e in pend[:limite]:
        key = e.get("key") or f"fuentes_src/{e['nicho']}/{e['clase']}/{e['carpeta']}/{e['archivo']}"
        mp4 = _tmp() / e["archivo"]
        if not r2io.bajar(key, mp4):
            continue
        r = _escuchar(mp4, fuente_de.get(e["nicho"], ""))
        mp4.unlink(missing_ok=True)
        if not r:
            continue
        clase = "TRADUCIR" if r["voz"] else "ASMR"
        txt = e.get("txt") or ""
        e["txt"] = (re.sub(r"clasificado :.*", _nota(clase, r), txt, count=1)
                    if "clasificado :" in txt else txt.rstrip() + "\n" + _nota(clase, r) + "\n")
        if clase != e["clase"]:
            log.info("%s: %s -> %s", e["archivo"][:44], e["clase"], clase)
        e["key"], e["clase"] = key, clase
        cambios += 1
        if cambios % 10 == 0:
            r2io.put_json(MANIFIESTO, man)
    if cambios and not r2io.put_json(MANIFIESTO, man):
        log.error("NO pude guardar el manifiesto.")
        return 1
    log.info("Revisados: %d", cambios)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["nuevos", "revisar"])
    ap.add_argument("--limite", type=int, default=10)
    ap.add_argument("--incluir-usados", action="store_true")
    a = ap.parse_args()
    if not r2io.en_nube():
        log.error("Esto es para la nube (falta PUERTA_R2_URL). En la PC: catalogar_fuente.py.")
        return 1
    if a.accion == "nuevos":
        return nuevos(a.limite)
    return revisar(a.limite, a.incluir_usados)


if __name__ == "__main__":
    raise SystemExit(main())
