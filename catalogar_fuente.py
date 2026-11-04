#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Baja TODO el perfil de la fuente y lo deja clasificado y listo para producir.

Qué hace
--------
1. Lista los videos del perfil (720 en Agrotonomy).
2. Baja cada uno que falte.
3. Escucha el audio LOCALMENTE (src/audio_voz) y decide:
      TRADUCIR  el original habla (casi siempre inglés) -> se traduce y se reemplaza
      ASMR      está mudo, solo ambiente               -> se le inventa un guion
      dudosos   no se pudo decidir                     -> lo resuelve Gemini después
4. Lo guarda en <destino>/<clase>/<tramo de vistas>/<tema>__<id>.mp4 con un .txt al lado.
5. Escribe catalogo.json con todo junto.

Por qué así
-----------
- LA CARPETA MANDA. Si mirás un video y ves que está mal clasificado, lo arrastrás de
  ASMR a TRADUCIR y listo: al volver a correr esto, la ubicación a mano le gana al
  filtro automático. El catálogo se regenera leyendo las carpetas.
- CLASIFICAR CON GEMINI SERÍAN 720 LLAMADAS y la cuota diaria gratis no da. El filtro
  local es gratis y, medido contra 39 videos ya etiquetados, acierta el 79% con 15% de
  dudosos y CERO errores del tipo peligroso (una voz tomada por muda, que es lo que
  haría publicar inglés y español pisándose).
- SE PUEDE CORTAR Y RETOMAR. Nada se re-descarga: si el archivo ya está en su carpeta,
  se saltea.

Uso:
    python catalogar_fuente.py                 # baja y clasifica todo lo que falte
    python catalogar_fuente.py --limite 20     # solo los 20 más vistos que falten
    python catalogar_fuente.py --solo-catalogo # no baja nada, rehace catalogo.json

    # Otro nicho: mismos pasos, otras fuentes y otro destino.
    python catalogar_fuente.py --fuente bonsai
    python catalogar_fuente.py --perfil https://www.tiktok.com/@x --destino "D:\\...""
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402  (carga el .env)
from src import audio_voz  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()

STAGING = ROOT / "downloads" / "_staging_fuente"
CLASES = {"voz": "TRADUCIR", "mudo": "ASMR", "dudoso": "dudosos", "sin_audio": "ASMR"}

# Las fuentes ya configuradas. Se elige con --fuente; sin eso, la de siempre.
FUENTES = {
    "agrotonomy": {
        "perfiles": ["https://www.tiktok.com/@agrotonomy"],
        "destino": r"C:\Users\Tomix\Desktop\S e r v i c i o s\Hydropony\@Agrotonomy",
        "vocabulario": "hidroponia",
    },
    "bonsai": {
        # Los dos primeros son los PRINCIPALES; los otros dos suman variedad.
        # @escuelaonline.bonsai tiene solo 27 videos pero la mediana más alta de las
        # cuatro (29.800 contra 3.571 del principal): pesa más de lo que sugiere su tamaño.
        "perfiles": ["https://www.tiktok.com/@elden_bonsai",
                     "https://www.tiktok.com/@bonsaiempire.com",
                     "https://www.tiktok.com/@mundobonsai_",
                     "https://www.tiktok.com/@escuelaonline.bonsai"],
        "destino": r"C:\Users\Tomix\Desktop\S e r v i c i o s\Bonsai\@Bonsais",
        "vocabulario": "bonsai",
    },
}

# Tramos por vistas. La lista cubre de mil a diez millones a propósito: los perfiles de
# hidroponía viven arriba (el menos visto de Agrotonomy tiene 43.400) y los de bonsái
# abajo (la mediana de @elden_bonsai es 3.571). Los tramos vacíos no se crean, así que
# la misma lista sirve para los dos sin llenar de carpetas vacías.
TRAMOS = [
    (10_000_000, None, "+10M"), (5_000_000, 10_000_000, "+5M"),
    (2_000_000, 5_000_000, "+2M"), (1_000_000, 2_000_000, "+1M"),
    (500_000, 1_000_000, "+500k"), (250_000, 500_000, "+250k"),
    (100_000, 250_000, "+100k"), (50_000, 100_000, "+50k"),
    (10_000, 50_000, "+10k"), (1_000, 10_000, "+1k"), (0, 1_000, "-1k"),
]

# --- nombre legible ---------------------------------------------------------------
# El vocabulario es POR FUENTE: con el de hidroponía, un video de bonsái no reconocería
# ni una palabra y todos los archivos se llamarían "general__<id>.mp4", que es
# exactamente lo que hace inútil el nombre legible.
CULTIVOS = {
    "lettuce": "lechuga", "cabbage": "repollo", "cabbages": "repollo", "basil": "albahaca",
    "parsley": "perejil", "dill": "eneldo", "tomato": "tomate", "tomatoes": "tomate",
    "strawberry": "frutilla", "strawberries": "frutilla", "pepper": "pimiento",
    "peppers": "pimiento", "eggplant": "berenjena", "eggplants": "berenjena",
    "zucchini": "zapallito", "broccoli": "brocoli", "cauliflower": "coliflor",
    "celery": "apio", "spinach": "espinaca", "kale": "kale", "mint": "menta",
    "cucumber": "pepino", "cucumbers": "pepino", "chili": "aji", "chilli": "aji",
    "watermelon": "sandia", "melon": "melon", "melons": "melon", "onion": "cebolla",
    "garlic": "ajo", "thyme": "tomillo", "leek": "puerro", "leeks": "puerro",
    "brassica": "brasicas", "brassicas": "brasicas", "arugula": "rucula",
    "chard": "acelga", "coriander": "cilantro", "cilantro": "cilantro",
    "oregano": "oregano", "rosemary": "romero", "sage": "salvia", "bean": "poroto",
    "beans": "poroto", "pea": "arveja", "peas": "arveja", "radish": "rabanito",
    "turnip": "nabo", "carrot": "zanahoria", "kang": "kangkong", "okra": "okra",
    "pumpkin": "zapallo", "squash": "zapallo", "corn": "maiz", "potato": "papa",
    "herbs": "hierbas", "microgreens": "microverdes", "flowers": "flores",
}
ACCIONES = {
    "harvest": "cosecha", "harvesting": "cosecha", "growing": "cultivo", "grow": "cultivo",
    "seed": "desde-semilla", "roots": "raices", "root": "raices",
    "transplant": "trasplante", "germination": "germinacion", "timelapse": "timelapse",
    "lapse": "timelapse", "density": "densidad", "pruning": "poda", "prune": "poda",
    "nutrients": "nutrientes", "heatwave": "calor", "heatwaves": "calor",
    "winter": "invierno", "summer": "verano", "pests": "plagas", "pest": "plagas",
    "cleaning": "limpieza", "assembly": "armado", "build": "armado",
    "comparison": "comparacion", "mixing": "mezcla", "spacing": "espaciado",
    "yield": "rendimiento", "greenhouse": "invernadero", "outdoor": "exterior",
}

# Bonsái: especies y técnicas. Muchos términos NO se traducen porque en el mundo del
# bonsái se usan en japonés tal cual (jin, shari, nebari, yamadori) y traducirlos haría
# el nombre menos reconocible, no más.
ESPECIES_BONSAI = {
    "juniper": "junipero", "juniperus": "junipero", "ficus": "ficus", "pine": "pino",
    "pinus": "pino", "maple": "arce", "acer": "arce", "azalea": "azalea",
    "elm": "olmo", "ulmus": "olmo", "wisteria": "glicina", "cherry": "cerezo",
    "sakura": "cerezo", "oak": "roble", "boxwood": "boj", "jade": "jade",
    "olive": "olivo", "olea": "olivo", "pomegranate": "granado",
    "bougainvillea": "buganvilla", "spruce": "picea", "larch": "alerce",
    "cypress": "cipres", "cedar": "cedro", "hornbeam": "carpe", "beech": "haya",
    "willow": "sauce", "bamboo": "bambu", "fig": "higuera", "apple": "manzano",
    "citrus": "citrico", "lemon": "limonero", "carmona": "carmona",
    "serissa": "serissa", "zelkova": "zelkova", "podocarpus": "podocarpus",
    "schefflera": "schefflera", "portulacaria": "portulacaria",
}
TECNICAS_BONSAI = {
    "wiring": "alambrado", "wire": "alambrado", "pruning": "poda", "prune": "poda",
    "trimming": "poda", "repotting": "trasplante", "repot": "trasplante",
    "defoliation": "defoliacion", "defoliate": "defoliacion", "styling": "estilizado",
    "style": "estilizado", "root": "raices", "roots": "raices", "nebari": "nebari",
    "deadwood": "madera-muerta", "jin": "jin", "shari": "shari", "grafting": "injerto",
    "graft": "injerto", "watering": "riego", "water": "riego", "soil": "sustrato",
    "akadama": "sustrato", "seedling": "plantin", "seed": "desde-semilla",
    "cutting": "esqueje", "cuttings": "esqueje", "layering": "acodo",
    "yamadori": "yamadori", "collected": "yamadori", "cascade": "cascada",
    "forest": "bosque", "shohin": "shohin", "mame": "mame", "kokedama": "kokedama",
    "moss": "musgo", "pot": "maceta", "fertilizer": "abono", "fertilizing": "abono",
    "pests": "plagas", "winter": "invierno", "summer": "verano",
    "beginner": "principiante", "progression": "evolucion", "timelapse": "timelapse",
    "transformation": "transformacion", "before": "antes-despues",
}

VOCABULARIOS = {
    "hidroponia": (CULTIVOS, ACCIONES),
    "bonsai": (ESPECIES_BONSAI, TECNICAS_BONSAI),
}


def _sin_tildes(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tema(titulo: str, vocabulario: str = "hidroponia") -> str:
    """Nombre corto y legible sacado del título. 'general' si no se reconoce nada.

    Se pone el SUJETO primero (el cultivo, la especie) porque es como se busca ('los de
    lechuga', 'los de junípero') y porque al ordenar la carpeta por nombre, los de la
    misma serie caen juntos: eso sirve para elegir variedad en vez de hacer cinco
    anuncios del mismo tema.
    """
    sujetos, acciones = VOCABULARIOS.get(vocabulario, VOCABULARIOS["hidroponia"])
    pal = re.findall(r"[a-z]+", _sin_tildes(titulo))
    cult, acc, vistos = [], [], set()
    for p in pal:
        if p in sujetos and sujetos[p] not in vistos:
            cult.append(sujetos[p]); vistos.add(sujetos[p])
        elif p in acciones and acciones[p] not in vistos:
            acc.append(acciones[p]); vistos.add(acciones[p])
    partes = (cult[:2] + acc[:2]) or ["general"]
    return "-".join(partes)


def tramo(vistas: int) -> str:
    for a, b, nombre in TRAMOS:
        if vistas >= a and (b is None or vistas < b):
            return nombre
    return "-100k"


def listar(perfiles: list[str]) -> list[dict]:
    """Todos los videos de todos los perfiles, sin bajar nada.

    Si un perfil falla se sigue con los demás: no tiene sentido perder 900 videos
    porque uno de cuatro perfiles no responde en este momento.
    """
    import yt_dlp
    out, vistos = [], set()
    for perfil in perfiles:
        log.info("Listando %s…", perfil)
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                                   "extract_flat": True, "ignoreerrors": True}) as y:
                info = y.extract_info(perfil, download=False)
        except Exception as e:  # noqa: BLE001
            log.warning("  no pude listar %s (%s) — sigo con los demás.", perfil, str(e)[:80])
            continue
        # Con ignoreerrors=True, yt-dlp NO lanza excepción cuando el perfil falla:
        # devuelve None. Sin este chequeo el except de arriba no se entera y revienta con
        # AttributeError, tirando abajo la corrida entera por un perfil que no respondió.
        # TikTok falla de forma intermitente ("Unable to extract secondary user ID"), así
        # que esto pasa seguido.
        if not info:
            log.warning("  %s no devolvió nada (TikTok falla intermitente) — "
                        "sigo con los demás y se recupera en la próxima corrida.", perfil)
            continue
        n = 0
        for e in (info.get("entries") or []):
            if not (e and e.get("id")) or str(e["id"]) in vistos:
                continue
            vistos.add(str(e["id"]))
            n += 1
            out.append({"id": str(e["id"]), "titulo": (e.get("title") or "")[:200],
                        "vistas": int(e.get("view_count") or 0), "perfil": perfil})
        log.info("  %d videos.", n)
    return out


def ya_esta(vid: str, destino: Path) -> Path | None:
    """Si el video ya está en alguna carpeta del destino, devuelve su ruta.
    Se busca en TODAS: si se movió a mano, esa ubicación es la que vale."""
    for p in destino.rglob(f"*__{vid}.mp4"):
        return p
    return None


def _url_video(v: dict) -> str:
    """La URL del video en su perfil de origen. Con varios perfiles no se puede armar
    con un handle fijo: el video sería de otra cuenta y el link quedaría roto."""
    perfil = (v.get("perfil") or "").rstrip("/")
    return f"{perfil}/video/{v['id']}"


def ficha(v: dict, clase: str, medicion: dict, destino: Path) -> str:
    """El .txt que acompaña al video. La descripción de Gemini se agrega después,
    cuando el video se analice para producir: acá todavía no se gastó ninguna llamada."""
    return (
        f"{v['titulo']}\n\n"
        f"id          : {v['id']}\n"
        f"vistas      : {v['vistas']:,}\n"
        f"origen      : {_url_video(v)}\n"
        f"clasificado : {clase}  ({medicion.get('detalle', '')})\n"
        f"archivo     : {destino.name}\n\n"
        f"{'-' * 62}\n"
        f"DESCRIPCION DE GEMINI: (se completa al analizarlo para producir)\n"
    )


def procesar(args) -> dict:
    """Baja, clasifica y archiva UN video. No re-descarga nada que ya esté."""
    v, destino, vocabulario = args
    vid = v["id"]
    p = ya_esta(vid, destino)
    if p:
        return {**v, "clase": p.parent.parent.name, "tramo": p.parent.name,
                "archivo": str(p), "estado": "ya_estaba"}
    try:
        from src import download
        STAGING.mkdir(parents=True, exist_ok=True)
        crudo = Path(download.download_video(_url_video(v), STAGING))
    except Exception as e:  # noqa: BLE001
        return {**v, "estado": "fallo_descarga", "error": str(e)[:120]}

    med = audio_voz.analizar(crudo)
    clase = CLASES.get(med["clase"], "dudosos")
    carpeta = destino / clase / tramo(v["vistas"])
    carpeta.mkdir(parents=True, exist_ok=True)
    final = carpeta / f"{tema(v['titulo'], vocabulario)}__{vid}.mp4"
    shutil.move(str(crudo), str(final))
    final.with_suffix(".txt").write_text(ficha(v, clase, med, final), encoding="utf-8")
    return {**v, "clase": clase, "tramo": tramo(v["vistas"]), "archivo": str(final),
            "audio": med["clase"], "concentracion": med.get("concentracion"),
            "estado": "nuevo"}


def _ficha_leer(mp4: Path) -> dict:
    """Recupera del .txt lo que se sepa de un video. Es la red de seguridad para cuando
    TikTok no devuelve el perfil completo: el archivo está en disco y su ficha al lado,
    así que no hace falta volver a preguntarle a nadie."""
    txt = mp4.with_suffix(".txt")
    d = {}
    if not txt.is_file():
        return d
    try:
        cuerpo = txt.read_text(encoding="utf-8")
    except OSError:
        return d
    lineas = cuerpo.splitlines()
    if lineas:
        d["titulo"] = lineas[0].strip()
    for ln in lineas:
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "vistas":
            try:
                d["vistas"] = int(v.replace(",", "").replace(".", ""))
            except ValueError:
                pass
        elif k == "origen":
            d["origen"] = v
            d["perfil"] = v.rsplit("/video/", 1)[0] if "/video/" in v else ""
    return d


def escribir_catalogo(filas: list[dict], destino: Path) -> Path:
    """catalogo.json a partir de lo que hay EN DISCO, no de lo que TikTok haya querido
    listar esta vez.

    Por qué así: TikTok devuelve el perfil incompleto de forma intermitente (medido: 464
    videos en una corrida y 359 en la siguiente, mismo perfil). Armando el catálogo solo
    con lo listado, 105 videos que estaban en disco desaparecían del índice — y con
    ellos su título, sus vistas y su clasificación. El disco manda; el listado y el
    catálogo anterior solo aportan datos.
    """
    destino.mkdir(parents=True, exist_ok=True)
    out = destino / "catalogo.json"

    # 1) Lo que ya sabíamos. Conserva además lo que se agregó después (descripciones de
    #    Gemini, guiones hechos, reels producidos): eso no se puede regenerar.
    previo = {}
    if out.is_file():
        try:
            previo = json.loads(out.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            previo = {}

    # 2) Lo medido en esta corrida, por id.
    frescos = {f["id"]: f for f in filas if f.get("id")}

    # 3) El disco: la verdad sobre qué existe y en qué carpeta está.
    cat = {}
    for mp4 in destino.rglob("*__*.mp4"):
        vid = mp4.stem.split("__")[-1]
        f = frescos.get(vid, {})
        ant = previo.get(vid, {})
        ficha_txt = _ficha_leer(mp4) if not f else {}
        origen = f.get("perfil") and _url_video(f) or ant.get("origen") or ficha_txt.get("origen", "")
        cat[vid] = {
            "titulo": f.get("titulo") or ant.get("titulo") or ficha_txt.get("titulo", ""),
            "vistas": f.get("vistas", ant.get("vistas", ficha_txt.get("vistas", 0))),
            # La carpeta manda: si se movió un video a mano, esa es su clase.
            "clase": mp4.parent.parent.name, "tramo": mp4.parent.name,
            "archivo": mp4.name,
            "audio_local": f.get("audio", ant.get("audio_local")),
            "concentracion": f.get("concentracion", ant.get("concentracion")),
            "perfil": f.get("perfil") or ant.get("perfil") or ficha_txt.get("perfil", ""),
            "origen": origen,
            # Lo que se agrega más adelante NO se pisa al regenerar.
            "descripcion": ant.get("descripcion"),
            "guiones_hechos": ant.get("guiones_hechos", []),
            "reels_producidos": ant.get("reels_producidos", []),
        }

    huerfanos = [v for v in previo if v not in cat]
    if huerfanos:
        log.warning("%d video(s) estaban en el catálogo y ya no están en disco: %s",
                    len(huerfanos), ", ".join(huerfanos[:5]))
    out.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0, help="solo los N más vistos que falten")
    ap.add_argument("--solo-catalogo", action="store_true")
    ap.add_argument("--hilos", type=int, default=3,
                    help="descargas en paralelo (3 es prudente: TikTok limita)")
    ap.add_argument("--fuente", default="agrotonomy", choices=sorted(FUENTES),
                    help="qué fuente catalogar (perfiles + destino + vocabulario)")
    ap.add_argument("--perfil", action="append", default=None,
                    help="perfil suelto; se puede repetir. Pisa los de --fuente")
    ap.add_argument("--destino", default=None, help="carpeta destino; pisa la de --fuente")
    a = ap.parse_args()

    f = FUENTES[a.fuente]
    perfiles = a.perfil or f["perfiles"]
    destino = Path(a.destino or f["destino"])
    vocabulario = f["vocabulario"]
    log.info("Fuente '%s' · %d perfil(es) -> %s", a.fuente, len(perfiles), destino)

    vids = sorted(listar(perfiles), key=lambda x: -x["vistas"])
    log.info("%d videos en total (sin repetidos entre perfiles).", len(vids))
    if not vids:
        log.error("No se pudo listar ningún perfil. Revisá la conexión y volvé a correrlo.")
        return 1

    if a.solo_catalogo:
        # Se le pasa TODO lo listado (no solo lo que ya está en disco): escribir_catalogo
        # recorre el disco por su cuenta y usa esto nada más que para poner al día título
        # y vistas.
        out = escribir_catalogo(vids, destino)
        log.info("Catálogo rehecho -> %s", out)
        return 0

    pendientes = [v for v in vids if not ya_esta(v["id"], destino)]
    if a.limite:
        pendientes = pendientes[:a.limite]
    log.info("Faltan %d por bajar (de %d).", len(pendientes), len(vids))

    filas, hechos = [], 0
    tareas = [(v, destino, vocabulario) for v in pendientes]
    with ThreadPoolExecutor(max_workers=max(1, a.hilos)) as ex:
        for r in ex.map(procesar, tareas):
            filas.append(r)
            hechos += 1
            if r.get("estado") == "fallo_descarga":
                log.warning("[%d/%d] %s NO se pudo bajar: %s",
                            hechos, len(pendientes), r["id"], r.get("error", "")[:70])
            else:
                log.info("[%d/%d] %-8s %-6s %s",
                         hechos, len(pendientes), r.get("clase"), r.get("tramo"),
                         Path(r["archivo"]).name[:58])

    # El catálogo se arma leyendo el disco entero, no solo lo de esta corrida ni solo lo
    # que TikTok haya querido listar.
    out = escribir_catalogo(vids, destino)
    import json as _json
    cat = _json.loads(out.read_text(encoding="utf-8"))

    from collections import Counter
    c = Counter(v["clase"] for v in cat.values())
    log.info("=" * 60)
    log.info("EN DISCO: %d videos (%d listados en esta corrida)", len(cat), len(vids))
    for k, n in c.most_common():
        log.info("   %-10s %4d", k, n)
    fallos = [x for x in filas if x.get("estado") == "fallo_descarga"]
    if fallos:
        log.warning("No se pudieron bajar %d (volvé a correrlo y los reintenta).", len(fallos))
    faltan = len([v for v in vids if not ya_esta(v["id"], destino)])
    if faltan:
        log.warning("Quedan %d listados que todavía no están en disco.", faltan)
    log.info("Catálogo -> %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
