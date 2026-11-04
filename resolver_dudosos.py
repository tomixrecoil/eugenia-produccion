#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Los videos que el filtro local no supo clasificar, resueltos escuchándolos con Gemini.

El filtro de src/audio_voz decide gratis y acierta la mayoría, pero deja una franja
"dudoso" a propósito: prefiere gastar una llamada antes que equivocarse y mandar a
inventar un guion sobre un video que ya habla en inglés. Esto resuelve esa franja y
mueve cada video a su carpeta definitiva.

Se reparte entre las 3 cuentas de AI Studio porque la cuota diaria gratuita es por
cuenta y ya frenó dos veces en una tarde.

Uso:
    python resolver_dudosos.py                # resuelve todos los que haya
    python resolver_dudosos.py --limite 15    # de a tandas, si la cuota aprieta
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()

# Las mismas fuentes que catalogar_fuente.py, para no tener dos listas que se separen.
from catalogar_fuente import FUENTES  # noqa: E402

# Se sobrescriben en main() según --fuente. Quedan a nivel de módulo porque resolver()
# corre en hilos y necesita verlas.
DESTINO = Path(FUENTES["agrotonomy"]["destino"])
DUDOSOS = DESTINO / "dudosos"

# El tema entra en la pregunta: "una granja vertical" con videos de bonsái confunde al
# modelo en vez de ayudarlo. Lo demás es igual para cualquier nicho.
TEMAS = {"agrotonomy": "una granja vertical", "bonsai": "bonsáis y jardinería"}
TEMA = TEMAS["agrotonomy"]


def pregunta_para(tema: str) -> str:
    return (
        f"Escucha este audio de un video de {tema}. Responde EXACTAMENTE en "
        "3 líneas, sin nada más:\n"
        "VOZ_HUMANA_HABLANDO: si|no\n"
        "IDIOMA: ingles|espanol|otro|ninguno\n"
        "QUE_SE_ESCUCHA: (una frase corta)\n\n"
        "OJO: música cantada, una guitarra o ruidos de manipular objetos NO son una voz "
        "humana hablando. Solo cuenta si alguien está NARRANDO o EXPLICANDO."
    )


def _claves() -> list[str]:
    import os
    out = []
    for n in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3",
              "GEMINI_API_KEY_4", "GEMINI_API_KEY_5"):
        v = (os.getenv(n) or "").strip()
        if v and v not in out:
            out.append(v)
    return out


# La cuota diaria gratuita es POR CUENTA Y POR MODELO. Con un solo modelo se agota a
# los ~20 pedidos y quedan videos sin resolver; probando varios se multiplica el
# presupuesto sin pagar nada. El lite va primero porque para esto —decir si hay alguien
# hablando— alcanza de sobra y tiene la cuota más holgada.
MODELOS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash"]


def escuchar(mp4: Path, claves: list[str]) -> dict:
    """Pregunta a Gemini si hay alguien hablando. Sube SOLO el audio (30 s), no el
    video: es una fracción del peso y de la cuota.

    Prueba cada modelo en cada cuenta hasta que uno conteste. Solo se rinde cuando se
    agotaron todas las combinaciones.
    """
    from google import genai
    tmp = Path(tempfile.gettempdir()) / f"dud_{mp4.stem[:40]}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4),
                    "-vn", "-ac", "1", "-ar", "16000", "-t", "30", str(tmp)],
                   capture_output=True, timeout=240)
    txt, ultimo = None, None
    for clave in claves:
        cli = genai.Client(api_key=clave)
        try:
            u = cli.files.upload(file=str(tmp))
            while u.state.name == "PROCESSING":
                time.sleep(2)
                u = cli.files.get(name=u.name)
        except Exception as e:  # noqa: BLE001
            ultimo = e
            continue
        for modelo in MODELOS:
            try:
                txt = cli.models.generate_content(
                    model=modelo, contents=[pregunta_para(TEMA), u]).text
                break
            except Exception as e:  # noqa: BLE001
                ultimo = e
        if txt:
            break
    try:
        tmp.unlink()
    except OSError:
        pass
    if not txt:
        raise RuntimeError(str(ultimo)[:130])
    hay = re.search(r"VOZ_HUMANA_HABLANDO:\s*(si|no)", txt, re.I)
    idi = re.search(r"IDIOMA:\s*(\w+)", txt, re.I)
    que = re.search(r"QUE_SE_ESCUCHA:\s*(.+)", txt, re.I)
    return {"voz": bool(hay and hay.group(1).lower() == "si"),
            "idioma": (idi.group(1).lower() if idi else "?"),
            "que": (que.group(1).strip()[:90] if que else "")}


def resolver(args) -> dict:
    mp4, claves = args
    try:
        r = escuchar(mp4, claves)
    except Exception as e:  # noqa: BLE001
        return {"archivo": mp4, "error": str(e)[:110]}
    # Un video con narración se TRADUCE. Uno sin narración recibe un guion nuevo.
    # El idioma español también va a TRADUCIR: ya habla, no hay que inventarle nada.
    clase = "TRADUCIR" if r["voz"] else "ASMR"
    carpeta = DESTINO / clase / mp4.parent.name
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / mp4.name
    shutil.move(str(mp4), str(destino))
    # El .txt viaja con el video y se le anota quién decidió y por qué.
    txt = mp4.with_suffix(".txt")
    if txt.is_file():
        cuerpo = txt.read_text(encoding="utf-8")
        cuerpo = cuerpo.replace(
            "clasificado : dudosos",
            f"clasificado : {clase}  (lo escuchó Gemini: "
            f"voz={'si' if r['voz'] else 'no'}, idioma={r['idioma']} — {r['que']})")
        destino.with_suffix(".txt").write_text(cuerpo, encoding="utf-8")
        txt.unlink()
    return {"archivo": destino, "clase": clase, **r}


def main() -> int:
    global DESTINO, DUDOSOS, TEMA
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--fuente", default="agrotonomy", choices=sorted(FUENTES),
                    help="qué catálogo resolver")
    a = ap.parse_args()

    DESTINO = Path(FUENTES[a.fuente]["destino"])
    DUDOSOS = DESTINO / "dudosos"
    TEMA = TEMAS.get(a.fuente, "jardinería")
    log.info("Fuente '%s' -> %s", a.fuente, DESTINO)

    pend = sorted(DUDOSOS.rglob("*.mp4"))
    if a.limite:
        pend = pend[:a.limite]
    if not pend:
        log.info("No quedan dudosos.")
        return 0
    claves = _claves()
    log.info("%d dudosos, repartidos en %d cuentas de AI Studio.", len(pend), len(claves))

    # A cada video se le pasan TODAS las cuentas, empezando por una distinta, para
    # repartir la carga sin perder el respaldo si la primera se queda sin cuota.
    tareas = [(p, claves[i % len(claves):] + claves[:i % len(claves)])
              for i, p in enumerate(pend)]
    res = []
    # 2 en paralelo: con más, las cuotas por minuto empiezan a rebotar.
    with ThreadPoolExecutor(max_workers=2) as ex:
        for i, r in enumerate(ex.map(resolver, tareas), 1):
            res.append(r)
            if r.get("error"):
                log.warning("[%d/%d] %s -> %s", i, len(pend),
                            Path(r["archivo"]).name[:48], r["error"])
            else:
                log.info("[%d/%d] %-8s %s", i, len(pend), r["clase"],
                         Path(r["archivo"]).name[:52])

    ok = [r for r in res if not r.get("error")]
    from collections import Counter
    c = Counter(r["clase"] for r in ok)
    log.info("=" * 58)
    log.info("Resueltos %d de %d — ASMR %d · TRADUCIR %d",
             len(ok), len(pend), c["ASMR"], c["TRADUCIR"])
    quedan = len(list(DUDOSOS.rglob("*.mp4")))
    if quedan:
        log.warning("Quedan %d sin resolver (volvé a correrlo).", quedan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
