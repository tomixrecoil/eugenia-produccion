#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Produce reels y los deja LISTOS en R2 para que Eugenia los publique sin la PC.

Por qué existe
--------------
El Worker de Cloudflare no tiene ffmpeg: no puede armar un video. Con un stock
pre-renderizado en R2, publicar es una llamada a la API de Meta que el Worker hace solo.

Cómo se escribe el guion (UNIFICADO 15/08)
------------------------------------------
Acá NO hay prompt propio. El guion sale del MISMO camino que los reels diarios:
  1. `analyze.analyze_video`  -> Gemini MIRA el video y devuelve la descripción
  2. `dubbing.spanish_script` -> escribe la voz con prompts/voz_describe.txt (+ el piso
                                  anti-IA/neutro/CTA de voz_comun.txt)
Antes había un prompt paralelo incrustado acá (la fórmula de 5 pasos): los 34 guiones
salieron todos iguales ("Imagina...") y el alcance se desplomó. Nunca más un prompt
paralelo: si hay que cambiar cómo se escribe un guion, se edita prompts/ desde la app
y vale para TODO. Lo único que sigue siendo de acá es el COPY del posteo (bloque de
oferta con el formato de Tomix).

Respeta la regla de repetición (ver registro_fuentes.py) y el filtro por huella MD5
(el mismo video bajado dos veces con IDs distintos no entra dos veces).

Uso:
    python producir_stock.py --nicho bonsai --cantidad 3
    python producir_stock.py --listar
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.logging_setup import get_logger  # noqa: E402

log = get_logger()

# Dónde vive el material catalogado de cada nicho. Es lo único que NO está en el YAML
# (la carpeta la eligió Tomix a mano y no se deduce del perfil de TikTok: el de bonsái
# es @elden_bonsai y la carpeta se llama @Bonsais).
CARPETA = {"bonsai": Path(r"C:/Users/Tomix/Desktop/S e r v i c i o s/Bonsai/@Bonsais"),
           "hidroponia": Path(r"C:/Users/Tomix/Desktop/S e r v i c i o s/Hydropony/@Agrotonomy")}


def carpeta_de(nicho: str) -> Path:
    """La carpeta de videos fuente del nicho. El que no tenga una propia cae en
    downloads/<nicho>, que es donde el pipeline deja lo que descarga: así un nicho nuevo
    devuelve 'no quedan fuentes' en vez de reventar con KeyError y cortar la tanda.
    En la nube (FUENTES_DIR) es la carpeta temporal donde se bajan de R2."""
    if os.getenv("FUENTES_DIR"):
        return Path(os.environ["FUENTES_DIR"]) / nicho
    return CARPETA.get(nicho) or (ROOT / "downloads" / nicho)


def _ficha(nicho: str):
    """La config del nicho, o None si no se puede leer. Lo que sale de acá alimenta el
    copy: un YAML ausente o roto no tiene por qué voltear la producción."""
    try:
        return config.load_niche(nicho)
    except Exception:  # noqa: BLE001
        return None


def _buckets(base: Path) -> list[Path]:
    """Las carpetas de vistas que hay DE VERDAD, de más vistas a menos.

    Antes era una lista fija de 4 nombres (+100k, +10k, +1k, general) mientras
    recategorizar_asmr.py crea 11 (+10M … -1k): las carpetas que no estaban en
    esa lista eran INVISIBLES. En hidroponía eso escondía 94 de 131 fuentes
    verificadas, justo las mejores (+1M, +2M, +5M). Descubrirlas en vivo evita
    que las dos listas se vuelvan a desincronizar.
    """
    if not base.is_dir():
        return []
    return sorted([d for d in base.iterdir() if d.is_dir() and not _no_usar(d)],
                  key=lambda d: _peso(d.name), reverse=True)


def _peso(nombre: str) -> tuple:
    """Orden de una carpeta de vistas (+5M antes que +1k); 'general' y otras, al final."""
    m = re.fullmatch(r"([+-])(\d+)([kKmM]?)", nombre)
    if not m:
        return (-1, 0)
    signo, num, uni = m.groups()
    mult = {"k": 1_000, "m": 1_000_000, "": 1}[uni.lower()]
    return (1 if signo == "+" else 0, int(num) * mult)


# Carpeta "dontuse" (pedido de Tomix, 19/10/2026): ahí van las fuentes que NO se usan
# nunca (las que duran menos de lo que funcionó: 45 s en hidroponía, 35 s en bonsái).
# Vive en <carpeta del nicho>/dontuse; la lista de lo movido está en _movidos.json.
NO_USAR = "dontuse"


def _texto_quemado(mp4: Path) -> bool:
    """True si el video trae subtítulos o texto sobreimpreso del creador original.
    Encima van los nuestros y sale con subtítulos DOBLES (pasó con 3 de 3 pruebas de
    bonsái, 19/10/2026). Gemini mira 3 cuadros; el resultado queda anotado en el .txt
    de la fuente ("texto_quemado : si|no") para no volver a preguntar. Si no se puede
    saber, devuelve False (no frena la producción)."""
    txt = mp4.with_suffix(".txt")
    cuerpo = txt.read_text(encoding="utf-8", errors="ignore") if txt.is_file() else ""
    m = re.search(r"texto_quemado\s*:\s*(si|no)", cuerpo)
    if m:
        return m.group(1) == "si"
    try:
        from google.genai import types as gt
        from src import videoedit
        from src import gemini_client
        dur = videoedit.probe_duration(mp4)
        partes = []
        for frac in (0.2, 0.5, 0.8):
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{dur * frac:.2f}", "-i", str(mp4),
                                "-frames:v", "1", "-vf", "scale=540:-1", "-f", "image2pipe",
                                "-vcodec", "mjpeg", "-"], capture_output=True, timeout=60)
            if r.stdout:
                partes.append(gt.Part.from_bytes(data=r.stdout, mime_type="image/jpeg"))
        if not partes:
            return False
        pregunta = ("Son cuadros de un mismo video. ¿Tiene SUBTÍTULOS o TEXTO SOBREIMPRESO agregado "
                    "en la edición (palabras escritas encima de la imagen)? No cuentan los carteles, "
                    "etiquetas o marcas que existen en la escena real. Responde solo: SI o NO.")
        resp = gemini_client.run(lambda c: gemini_client.generate(
            c, os.getenv("GEMINI_MODEL") or "gemini-3.6-flash", partes + [pregunta]))
        si = (getattr(resp, "text", "") or "").strip().upper().startswith("SI")
        txt.write_text(cuerpo.rstrip() + f"\ntexto_quemado : {'si' if si else 'no'}\n", encoding="utf-8")
        return si
    except Exception as e:  # noqa: BLE001
        log.warning("No pude revisar texto quemado de %s (%s).", mp4.name[:40], str(e)[:80])
        return False


def _tiene_video(mp4: Path) -> bool:
    """True si el mp4 tiene imagen. Hay fuentes que bajaron con SOLO el audio: Gemini
    las rechaza ("falló al procesar el video") y se reintentaban en cada corrida. Si
    ffprobe no anda, responde True para no frenar la producción."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v",
                            "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(mp4)],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return True
    return r.returncode != 0 or "video" in r.stdout


def _a_dontuse(mp4: Path, nicho: str, motivo: str) -> None:
    """Manda la fuente (y su .txt) a <carpeta del nicho>/dontuse/<motivo>/<clase>/<vistas>.
    En la nube la carpeta es temporal: se anota en el registro de R2 como usada, así ni
    la nube ni la PC la vuelven a elegir."""
    import shutil
    import r2io
    if r2io.en_nube():
        import registro_fuentes
        tid = (re.search(r"__(\d+)", mp4.name) or [None, ""])[1]
        if tid:
            registro_fuentes.registrar(nicho, f"dontuse-{motivo}", tid, f"descartada: {motivo}")
        log.info("Fuente %s descartada (%s), anotada en R2.", mp4.name[:44], motivo)
        return
    raiz = carpeta_de(nicho)
    try:
        rel = mp4.parent.relative_to(raiz)
    except ValueError:
        rel = Path(mp4.parent.name)
    destino = raiz / NO_USAR / motivo / rel
    destino.mkdir(parents=True, exist_ok=True)
    for h in mp4.parent.glob(mp4.stem + ".*"):
        shutil.move(str(h), str(destino / h.name))
    log.info("Fuente %s -> dontuse/%s", mp4.name[:44], motivo)


def _no_usar(p: Path) -> bool:
    """True si el archivo o carpeta está dentro de una carpeta 'dontuse' (en cualquier
    nivel): esas fuentes no se tocan jamás."""
    return any(parte.lower() == NO_USAR for parte in p.parts)
# El tema con la aclaración entre paréntesis: al modelo la palabra sola ("bonsái") no le
# alcanza para saber de qué va el curso. Manda sobre el campo `tema` del YAML, que es el
# nombre pelado.
TEMA = {"bonsai": "bonsái (arte de árboles en miniatura)",
        "hidroponia": "hidroponía (cultivo sin tierra)",
        "terrarios": "terrarios (pequeños ecosistemas de plantas dentro de un frasco o vidrio)",
        "herbologia": "plantas medicinales (herbolaria: cultivar y usar plantas que sanan)"}
# Solo RESPALDO si el nicho no tiene cta_link cargado. La fuente de verdad es el campo
# "Link de venta (CTA)" de Ajustes -> Mi producto (switch landing/checkout): lo que
# Tomix elija ahí sale en el copy de TODOS los posteos, stock incluido.
# 14/11: las páginas de conocimientosdigital.pages.dev, no checkouts de Hotmart (el
# precio real lo sigue sacando sync_precios.py del checkout; acá no hace falta).
CHECKOUT_RESPALDO = {n: f"https://conocimientosdigital.pages.dev/{n}"
                     for n in ("bonsai", "hidroponia", "terrarios", "herbologia")}
AMBIENTE = 0.22          # cuánto del audio ambiente queda debajo de la voz
# Ritmo REAL de Antonio a velocidad 1, con datos y números (medido 19/10/2026: 195
# palabras = 84 s). Las palabras del guion = duración del video x esto x velocidad del
# panel, para que la narración cubra el video entero sin pasarse.
# Fuentes de reserva por tanda: si un video falla, se prueba el siguiente (ver _producir).
RESERVAS = 2

PALABRAS_POR_SEG = 2.6  # medido 19/10 a x2: 4,5-5,5 palabras/s; se apunta un poco largo (si sobra, se congela el final)


def _velocidad(niche) -> float:
    """La velocidad de la voz del panel (pestaña Nicho). Antes el stock la ignoraba y
    mandaba siempre 1.0: cambiarla en el panel no hacía nada en estos videos."""
    try:
        return max(0.5, min(3.0, float(getattr(niche, "voice_speed", 1.0) or 1.0)))
    except (TypeError, ValueError):
        return 1.0


def _zona_mockup(niche, w: int, h: int, logo: Path) -> tuple[int, int]:
    """(arriba, abajo) en píxeles del espacio libre para el mockup: debajo del logo y
    encima de los subtítulos, con un margen de aire. Así el mockup puede ser grande
    sin tapar ninguno de los dos (pedido de Tomix, 19/10/2026)."""
    k = h / 1920.0                                   # los subs se escriben en 1080x1920
    arriba = int(60 * k)
    pos_logo = str(getattr(niche, "logo_position", "top") or "top")
    if getattr(niche, "add_logo", False) and logo.exists() and pos_logo.startswith("top"):
        try:
            from PIL import Image
            lw, lh = Image.open(logo).size
            alto_logo = w * float(niche.logo_scale or 0.35) * lh / max(lw, 1)
        except Exception:  # noqa: BLE001
            alto_logo = w * 0.35
        arriba = int(40 + alto_logo + 8 * k)
    margen = float(getattr(niche, "subtitle_margin_v", 520) or 520)
    fuente = float(getattr(niche, "subtitle_font_size", 92) or 92)
    # Alto del renglón: con Arial Black 92 se usaba 1,4x (con aire). Con la letra
    # gigante del estilo viral (Baloo 234, 02/11/2026) el texto real mide ~0,8x: medido,
    # el borde de arriba queda 182 px sobre el margen. 1,4x le robaba 140 px al mockup.
    alto_subs = fuente * (1.4 if fuente <= 120 else 0.85)
    tope_subs = h - (margen + alto_subs) * k        # los subtítulos son de 1 renglón (máx ~18 letras)
    abajo = int(tope_subs - 8 * k)
    return arriba, abajo


def tema_de(nicho: str) -> str:
    """Cómo se nombra el tema del curso en el copy."""
    return TEMA.get(nicho) or getattr(_ficha(nicho), "tema", "") or nicho


def checkout_de(nicho: str) -> str:
    """El link que va en el copy cuando el nicho no tiene cta_link. Se usa la landing
    antes que el checkout: mandar a alguien directo a pagar sin ver la oferta vende menos."""
    if nicho in CHECKOUT_RESPALDO:
        return CHECKOUT_RESPALDO[nicho]
    f = _ficha(nicho)
    return getattr(f, "cta_landing", "") or getattr(f, "cta_checkout", "")


def total_en_stock() -> int:
    import armar_stock
    return len(armar_stock.leer_index())


def _usados() -> tuple[set, set]:
    """(IDs de TikTok ya usados, huellas MD5 ya usadas), del registro en R2."""
    try:
        import registro_fuentes
        reg = registro_fuentes._leer()
        return ({k.split(":", 1)[1] for k in reg},
                {v.get("md5") for v in reg.values() if v.get("md5")})
    except Exception:  # noqa: BLE001
        return set(), set()


def elegir_fuentes(nicho: str, cuantos: int, clase: str = "ASMR") -> list[Path]:
    """Los verificados con más vistas que todavía no se usaron, de la clase pedida
    (ASMR = mudo, se inventa guion; TRADUCIR = habla en otro idioma, se traduce)."""
    import registro_fuentes
    import r2io
    if r2io.en_nube():
        _bajar_candidatas(nicho, clase, maximo=cuantos + 4)
    base = carpeta_de(nicho) / clase
    usados, huellas = _usados()
    out = []
    por_creador: dict[str, int] = {}
    for d in _buckets(base):
        for mp4 in sorted(d.glob("*.mp4")):
            if _no_usar(mp4):
                continue
            m = re.search(r"__(\d+)", mp4.name)
            if not m or m.group(1) in usados:
                continue
            txt = mp4.with_suffix(".txt")
            cuerpo = txt.read_text(encoding="utf-8", errors="ignore") if txt.is_file() else ""
            if "revisado2" not in cuerpo:     # sin verificar NO se toca
                continue
            if not _tiene_video(mp4):          # bajado roto: solo audio (stk-bonsa-232902, 28/10)
                _a_dontuse(mp4, nicho, "sin_video")
                continue
            if _texto_quemado(mp4):            # subtítulos del creador -> saldrían dobles
                _a_dontuse(mp4, nicho, "texto_quemado")
                continue
            # Último filtro, y el que el ID no cubre: el MISMO video bajado dos veces con
            # IDs distintos. Se hashea recién acá (sobre los pocos candidatos que pasaron
            # los otros filtros), no sobre las 400 fuentes de las carpetas.
            h = registro_fuentes.huella(mp4)
            if h and h in huellas:
                log.info("Salteo %s: mismo contenido que una fuente ya usada.", mp4.name[:44])
                continue
            huellas.add(h)          # también evita repetir dentro de esta misma tanda
            if nicho in VARIAR_CREADORES:
                c = creador_de(cuerpo)
                if por_creador.get(c, 0) >= MAX_POR_CREADOR:
                    continue        # le toca a otro creador (no se marca como usado)
                por_creador[c] = por_creador.get(c, 0) + 1
            out.append(mp4)
            if len(out) >= cuantos:
                return out
    return out


# Plantas medicinales salió 8 de 8 del mismo TikToker (miremedionatural10) y cada video dos
# veces (traducido + muteado). Tomix, 18/11: "no puede ser una sola cuenta de TikTok".
# En estos nichos: como mucho MAX_POR_CREADOR por tanda, los candidatos se bajan
# alternando perfiles, y no hay segunda versión muteada/repetida del mismo video.
VARIAR_CREADORES = ("terrarios", "herbologia")
MAX_POR_CREADOR = 1


def creador_de(ficha_txt: str) -> str:
    m = re.search(r"tiktok\.com/@([\w.\-]+)", ficha_txt or "")
    return m.group(1).lower() if m else "?"


def _alternar_perfiles(vids: list[dict]) -> list[dict]:
    """Ordena por vistas DENTRO de cada perfil y después intercala: el mejor de cada uno,
    el segundo de cada uno... Así no se bajan 7 seguidos del perfil con más vistas."""
    grupos: dict[str, list[dict]] = {}
    for v in sorted(vids, key=lambda v: -v["vistas"]):
        grupos.setdefault((v.get("perfil") or "").rstrip("/").lower(), []).append(v)
    out, i = [], 0
    while any(i < len(g) for g in grupos.values()):
        out += [g[i] for g in grupos.values() if i < len(g)]
        i += 1
    return out


MANIFIESTO = "fuentes_src/manifest.json"

# Cuando se acaban las fuentes nuevas (pedido de Tomix, 28/10/2026: "se pueden repetir"
# y "usar los hablados sin audio"), la producción NO para:
#   MUTEADO  un video hablado (TRADUCIR) se usa SIN su audio, con guion nuevo como si
#            fuera ASMR. Una vez por fuente. El audio original se tira entero.
#   REPETIR  un ASMR ya usado vuelve con un guion nuevo (mismo camino que los nuevos;
#            clave). Solo si su último uso tiene más de DIAS_ENTRE_REPETICIONES.
DIAS_ENTRE_REPETICIONES = 21
MAX_USOS = 4


def _usos_de(nicho: str) -> dict:
    """{tiktok_id: [usos]} del registro de R2, para este nicho."""
    try:
        import registro_fuentes
        return {v.get("tiktok_id"): v.get("usos", []) for k, v in registro_fuentes._leer().items()
                if k.startswith(nicho + ":")}
    except Exception:  # noqa: BLE001
        return {}


def _apto_reuso(modo: str, usos: list) -> bool:
    from datetime import datetime, timedelta
    angulos = [str(u.get("angulo", "")) for u in usos]
    if any(a.startswith("descartada") for a in angulos):
        return False
    if modo == "MUTEADO":
        return not any(a.startswith("muteado") for a in angulos)
    # REPETIR: ya usado, pocas veces, y no hace poco.
    if not usos or len(usos) >= MAX_USOS:
        return False
    ultima = max((u.get("fecha") or "") for u in usos)
    limite = (datetime.now() - timedelta(days=DIAS_ENTRE_REPETICIONES)).strftime("%Y-%m-%d")
    return ultima <= limite


def elegir_reuso(nicho: str, cuantos: int, modo: str) -> list[Path]:
    """MUTEADO: hablados (TRADUCIR) que nunca salieron muteados. REPETIR: ASMR ya usados,
    los de uso más viejo primero."""
    import r2io
    clase = "TRADUCIR" if modo == "MUTEADO" else "ASMR"
    usos = _usos_de(nicho)
    if r2io.en_nube():
        _bajar_candidatas(nicho, clase, maximo=cuantos + 4,
                          filtro=lambda e: _apto_reuso(modo, usos.get(e.get("tid"), [])))
    cand = []
    for d in _buckets(carpeta_de(nicho) / clase):
        for mp4 in sorted(d.glob("*.mp4")):
            if _no_usar(mp4):
                continue
            m = re.search(r"__(\d+)", mp4.name)
            if not m or not _apto_reuso(modo, usos.get(m.group(1), [])):
                continue
            txt = mp4.with_suffix(".txt")
            if "revisado2" not in (txt.read_text(encoding="utf-8", errors="ignore") if txt.is_file() else ""):
                continue
            ultima = max([u.get("fecha") or "" for u in usos.get(m.group(1), [])] or [""])
            cand.append((ultima, mp4))
    if modo == "REPETIR":
        cand.sort(key=lambda x: x[0])           # el que hace más que no sale, primero
    out = []
    for _, mp4 in cand:
        if not _tiene_video(mp4):
            _a_dontuse(mp4, nicho, "sin_video")
            continue
        if _texto_quemado(mp4):
            _a_dontuse(mp4, nicho, "texto_quemado")
            continue
        out.append(mp4)
        if len(out) >= cuantos:
            break
    return out


def _bajar_candidatas(nicho: str, clase: str, maximo: int = 6, filtro=None) -> None:
    """Nube: baja de R2 las mejores fuentes sin usar a carpeta_de(nicho), con la misma
    forma de carpetas que en la PC. Así elegir_fuentes sigue igual de ahí en adelante.
    Se bajan pocas (las primeras `maximo` por vistas): cada una pesa 5-40 MB."""
    import r2io
    man = r2io.get_json(MANIFIESTO) or []
    usados, huellas = _usados()
    # filtro(entrada) reemplaza al "sin usar" de siempre: lo usan los muteados y las
    # repeticiones, que eligen justamente entre fuentes YA usadas.
    if filtro is None:
        def filtro(e):
            return e.get("tid") not in usados and e.get("md5") not in huellas
    cand = [e for e in man if e.get("nicho") == nicho and e.get("clase") == clase
            and "revisado2" in (e.get("txt") or "") and filtro(e)]
    cand.sort(key=lambda e: _peso(e.get("carpeta", "")), reverse=True)
    for e in cand[:maximo]:
        destino = carpeta_de(nicho) / clase / e["carpeta"] / e["archivo"]
        if destino.is_file():
            continue
        key = e.get("key") or f"fuentes_src/{nicho}/{clase}/{e['carpeta']}/{e['archivo']}"
        if r2io.bajar(key, destino):
            import registro_fuentes
            if e.get("md5") and registro_fuentes.huella(destino) != e["md5"]:
                log.warning("%s llegó distinto de lo subido (md5): no la uso.", e["archivo"][:44])
                destino.unlink(missing_ok=True)
                continue
            destino.with_suffix(".txt").write_text(e.get("txt") or "", encoding="utf-8")
        else:
            log.warning("No pude bajar %s de R2.", e["archivo"][:44])


# Fuentes A DEMANDA (14/11/2026, Tomix): terrarios y herbología no tienen catálogo (todavía
# no se sabe qué perfiles sirven, así que NO se catalogan en masa a las 01:00 como
# hidroponía y bonsái). Cuando a un nicho le faltan fuentes verificadas para la tanda del
# día, se listan los perfiles de TikTok PRENDIDOS de su yaml (sin bajar nada), se bajan
# SOLO las que faltan (de más vistas a menos, salteando las ya usadas o catalogadas), se
# escuchan con Gemini igual que en fuentes_nube y, si se pudieron escuchar, quedan con
# "revisado2" en la carpeta de siempre y en R2 (fuentes_src + manifiesto) para no
# rebajarlas. Las que Gemini no pudo escuchar se tiran: sin verificar no se usa nada.
# Un video con voz queda TRADUCIR (se dobla y se reemplaza el audio, nunca sale en inglés).
DESCARTADOS = "fuentes_src/descartados.json"


def _disponibles(man: list, nicho: str, usados: set, huellas: set) -> int:
    """Fuentes verificadas y sin usar del nicho en el manifiesto (ASMR o TRADUCIR)."""
    return sum(1 for e in man if e.get("nicho") == nicho
               and e.get("clase") in ("ASMR", "TRADUCIR")
               and "revisado2" in (e.get("txt") or "")
               and e.get("tid") not in usados and e.get("md5") not in huellas)


def _nombre_legible(titulo: str) -> str:
    """'general' o las primeras palabras del título sin tildes (es la pista del copy)."""
    import unicodedata
    t = unicodedata.normalize("NFKD", (titulo or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    pal = [w for w in re.findall(r"[a-z]+", t) if len(w) > 2][:4]
    return "-".join(pal)[:40] or "general"


def fuentes_a_demanda(nicho: str, cuantos: int) -> int:
    """Nube: si al nicho le faltan fuentes para `cuantos`, baja y verifica SOLO las que
    faltan. Devuelve cuántas dejó listas. No publica nada ni toca el pipeline viejo."""
    import r2io
    import registro_fuentes
    if not r2io.en_nube():
        return 0
    # Solo para los nichos que todavía no tienen catálogo (14/11, pedido de Tomix: "que se
    # produzcan con los que están en TikTok"). Hidroponía y bonsái usan su catálogo de siempre.
    if nicho not in ("terrarios", "herbologia"):
        return 0
    man = r2io.get_json(MANIFIESTO)
    man_ok = isinstance(man, list)
    man = man if man_ok else []
    usados, huellas = _usados()
    falta = cuantos - _disponibles(man, nicho, usados, huellas)
    if falta <= 0:
        return 0
    niche = _ficha(nicho)
    if niche is None:
        return 0
    perfiles = [u for u in config.fuentes_de(niche) if "tiktok.com" in (u or "")]
    if not perfiles:
        log.info("%s: sin perfiles de TikTok prendidos para buscar fuentes.", nicho)
        return 0
    import catalogar_fuente as cf
    import resolver_dudosos as rd
    from src import audio_voz, download
    conocidos = {e.get("tid") for e in man} | usados
    descartados = r2io.get_json(DESCARTADOS)
    conocidos |= set(descartados or [])
    nuevos_descartes: list[str] = []
    listados = cf.listar(perfiles)
    if not listados:
        # TikTok no deja listar perfiles desde yt-dlp (14/11: "Failed to parse JSON" en
        # todos). Respaldo: la lista de candidatos leída del perfil en el navegador (solo
        # id y vistas, sin bajar videos) en R2 fuentes_src/candidatos/<nicho>.json. Bajar
        # un video suelto sí funciona. Solo de los perfiles que siguen prendidos.
        prendidos = {u.rstrip("/").split("@")[-1] for u in perfiles}
        cand = (r2io.get_json(f"fuentes_src/candidatos/{nicho}.json") or {}).get("videos") or []
        listados = [{"id": c["id"], "vistas": int(c.get("vistas") or 0), "titulo": c.get("titulo") or c["perfil"],
                     "perfil": f"https://www.tiktok.com/@{c['perfil']}"}
                    # busqueda=true: sacados de la búsqueda de TikTok (18/11), de muchos
                    # creadores distintos; no dependen de los 4 perfiles del panel.
                    for c in cand if c.get("perfil") in prendidos or c.get("busqueda")]
        log.info("%s: listado de TikTok vacío; uso %d candidatos de R2.", nicho, len(listados))
    vids = _alternar_perfiles([v for v in listados if v["id"] not in conocidos])
    log.info("%s: faltan %d fuentes; %d videos sin usar en sus perfiles (bajo solo %d).",
             nicho, falta, len(vids), falta)
    rd.TEMA = tema_de(nicho)
    claves = rd._claves()
    listas = 0
    # Tope de bajadas: muchas se descartan (texto quemado), así que se sigue hasta tener
    # las que faltan. 23/11: con el tope en bajadas (no en listas) salía 0 todos los días.
    for v in vids[:falta * 10]:
        if listas >= falta:
            break
        destino_tmp = carpeta_de(nicho) / "_a_demanda"
        try:
            crudo = Path(download.download_video(cf._url_video(v), destino_tmp))
        except Exception as e:  # noqa: BLE001
            log.warning("No pude bajar %s (%s).", v["id"], str(e)[:80])
            continue
        if not _tiene_video(crudo):
            log.warning("%s bajó sin imagen: lo salteo.", v["id"])
            nuevos_descartes.append(v["id"])
            crudo.unlink(missing_ok=True)
            continue
        if _texto_quemado(crudo):           # antes de gastar una escucha de Gemini
            log.info("%s tiene texto quemado: lo salteo.", v["id"])
            nuevos_descartes.append(v["id"])
            crudo.unlink(missing_ok=True)
            continue
        h = registro_fuentes.huella(crudo)
        if h and h in huellas:
            log.info("%s: mismo contenido que una fuente ya usada.", v["id"])
            nuevos_descartes.append(v["id"])
            crudo.unlink(missing_ok=True)
            continue
        try:
            r = rd.escuchar(crudo, claves)
        except Exception as e:  # noqa: BLE001
            r = None
            log.warning("No pude escuchar %s (%s).", v["id"], str(e)[:80])
        if not r or r.get("idioma") in (None, "", "?"):
            log.warning("%s sin verificar (Gemini no lo escuchó): no lo uso.", v["id"])
            crudo.unlink(missing_ok=True)
            continue
        med = audio_voz.analizar(crudo)
        clase = "TRADUCIR" if r["voz"] else "ASMR"
        tramo = cf.tramo(v["vistas"])
        archivo = f"{_nombre_legible(v.get('titulo') or v['id'])}__{v['id']}.mp4"
        final = carpeta_de(nicho) / clase / tramo / archivo
        final.parent.mkdir(parents=True, exist_ok=True)
        crudo.replace(final)
        nota = (f"clasificado : {clase}  [revisado2: voz={'si' if r['voz'] else 'no'}, "
                f"idioma={r['idioma']} — {r['que']}]")
        txt = re.sub(r"clasificado :.*", nota, cf.ficha(v, clase, med, final), count=1)
        final.with_suffix(".txt").write_text(txt, encoding="utf-8")
        huellas.add(h)
        listas += 1
        log.info("+ a demanda %s %s %s %s", nicho, clase, tramo, archivo[:50])
        # A R2 para no rebajarla mañana. Si el manifiesto no se pudo leer NO se escribe
        # (pisaría el catálogo entero); la fuente igual queda lista para hoy.
        key = f"fuentes_src/{nicho}/{clase}/{tramo}/{archivo}"
        if man_ok and r2io.put_file(final, key, "video/mp4"):
            man.append({"nicho": nicho, "clase": clase, "carpeta": tramo, "archivo": archivo,
                        "tid": v["id"], "txt": txt, "md5": h, "key": key})
    # Para no volver a bajarlos mañana. Solo si la lista se pudo leer (si no, la pisaría).
    if nuevos_descartes and isinstance(descartados, list):
        r2io.put_json(DESCARTADOS, descartados + nuevos_descartes)
    if listas and man_ok and not r2io.put_json(MANIFIESTO, man):
        log.warning("No pude guardar el manifiesto: las fuentes de hoy sirven igual.")
    log.info("%s: %d fuentes nuevas listas a demanda.", nicho, listas)
    return listas


class CuotaAgotada(Exception):
    """Todos los intentos murieron por límite. NO significa "se acabó el día": el límite
    de Gemini es también POR MINUTO, así que casi siempre alcanza con esperar."""


def _es_cuota(e: Exception) -> bool:
    s = str(e).upper()
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "QUOTA" in s or "RATE LIMIT" in s


_FALLOS_PATH = ROOT / "state" / "fuentes_fallidas.json"


def _tercer_fallo(tid: str) -> bool:
    """Cuenta fallos (no de cuota) por video. True recién en el 3ro -- un fallo
    suelto puede ser un hipo transitorio de red, tres seguidos es un archivo roto.
    En la nube el disco se borra en cada corrida: la cuenta vive en R2."""
    import json
    import r2io
    if r2io.en_nube():
        datos = r2io.get_json("fuentes/fallidas.json") or {}
        datos[tid] = datos.get(tid, 0) + 1
        r2io.put_json("fuentes/fallidas.json", datos)
        return datos[tid] >= 3
    try:
        datos = json.loads(_FALLOS_PATH.read_text(encoding="utf-8")) if _FALLOS_PATH.is_file() else {}
    except Exception:  # noqa: BLE001
        datos = {}
    datos[tid] = datos.get(tid, 0) + 1
    try:
        _FALLOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _FALLOS_PATH.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return datos[tid] >= 3


def _gemini(prompt: str, nicho: str = "") -> str | None:
    """Texto corto con rotación de cuentas (solo para el COPY del posteo).
    Lleva la referencia de reels ganadores del nicho como instrucción de sistema."""
    from google import genai
    from google.genai import types as genai_types
    from src import referencia
    sistema_ref = referencia.como_sistema(nicho)
    cfg = genai_types.GenerateContentConfig(system_instruction=sistema_ref) if sistema_ref else None
    hubo_cuota = hubo_intento = False
    # Las 6 cuentas (la 6ta, sersoularacademiadeluz, faltaba en esta rotación).
    for n in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3",
              "GEMINI_API_KEY_4", "GEMINI_API_KEY_5", "GEMINI_API_KEY_6"):
        k = (os.getenv(n) or "").strip()
        if not k:
            continue
        # El cliente va en una VARIABLE, no encadenado: creado como temporal se cierra
        # antes de que llegue la respuesta y tira "the client has been closed".
        cli = genai.Client(api_key=k)
        for modelo in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-3.6-flash"):
            hubo_intento = True
            try:
                r = cli.models.generate_content(model=modelo, contents=prompt, config=cfg)
                if r.text:
                    return r.text
            except Exception as e:  # noqa: BLE001
                if _es_cuota(e):
                    hubo_cuota = True
                continue
    if hubo_intento and hubo_cuota:
        raise CuotaAgotada("las 6 cuentas de Gemini están en límite ahora mismo")
    return None


def guion_del_pipeline(nicho: str, niche, clave: str, mp4: Path, out: Path,
                       clase: str = "ASMR") -> str:
    """El guion por el camino OFICIAL: Gemini mira el video, la voz sale de prompts/.

    La descripción se cachea en el mismo archivo que usa el pipeline
    (descripcion_gemini.txt): re-ejecutar no vuelve a subir el video a Gemini.

    `clase`: "ASMR" (mudo) inventa el guion sobre la descripción visual, modo
    "describe". "TRADUCIR" (habla en otro idioma) traduce la transcripción real,
    modo "translate" — mismo camino que usan los reels diarios (ver
    src.pipeline._process_media), nunca se inventa un guion sobre un video que
    ya habla.
    """
    from src import analyze, dubbing, videoedit
    from src.pipeline import _split_analysis

    secrets = config.load_secrets()
    cache = out / "descripcion_gemini.txt"
    if cache.is_file() and len(cache.read_text(encoding="utf-8", errors="ignore")) > 80:
        descripcion = cache.read_text(encoding="utf-8", errors="ignore")
        log.info("Descripción cacheada (%d chars): no re-subo el video.", len(descripcion))
    else:
        descripcion = analyze.analyze_video(mp4, niche.gemini_prompt,
                                            secrets.gemini_api_key, secrets.gemini_model)
        out.mkdir(parents=True, exist_ok=True)
        cache.write_text(descripcion, encoding="utf-8")
    transcripcion, visual = _split_analysis(descripcion)
    modo = "translate" if clase == "TRADUCIR" else "describe"
    fuente_texto = (transcripcion if clase == "TRADUCIR" else visual) or descripcion
    # SIN TOPE (19/10/2026, pedido de Tomix): antes había un tope fijo de 42 s y todos
    # los guiones salían cortos. Ahora Gemini recibe la duración REAL del video, la
    # velocidad de la voz y cuántas palabras entran, y escribe para cubrirlo entero. Si
    # igual se pasa, se acorta (dubbing) y como red de seguridad se congela el final.
    dur_video = videoedit.probe_duration(mp4)
    velocidad = _velocidad(niche)
    palabras = int(dur_video * PALABRAS_POR_SEG * velocidad)
    # Cascada de MODELOS, no solo de cuentas: cada modelo tiene su propia cuota diaria.
    # El 15/08 las 3 cuentas agotaron gemini-2.5-flash y el re-doblaje quedó girando en
    # vacío toda la noche, con flash-lite intacto. Para un guion de 40 palabras
    # cualquiera de los tres alcanza.
    ultimo = None
    # gemini-2.0-flash-lite fue dado de baja por Google (404 del 18/08: "no longer
    # available, update to gemini-3.6-flash") y rompia el fallback justo cuando mas
    # falta hacia (flash-latest sin cuota -> caia a un modelo muerto).
    for m in dict.fromkeys([secrets.gemini_model, "gemini-flash-latest",
                            "gemini-3.6-flash"]):
        try:
            return dubbing.spanish_script(modo, fuente_texto, dur_video,
                                          secrets.gemini_api_key, m,
                                          video_id=clave, nicho=nicho,
                                          palabras=palabras, velocidad=velocidad)
        except Exception as e:  # noqa: BLE001
            ultimo = e
            if _es_cuota(e):
                log.warning("Modelo %s sin cuota: pruebo el siguiente.", m)
                continue
            raise
    raise CuotaAgotada(f"sin cuota de texto en todos los modelos ({str(ultimo)[:60]})")


def copy_posteo(nicho: str, pista: str, link: str = "", descripcion: str = "",
                guion: str = "") -> str | None:
    """El copy del posteo, con el bloque de oferta EXACTO que definió Tomix.
    `descripcion` (lo que se ve + lectura de venta) y `guion` (lo que dice la voz): el copy
    depende de las dos cosas (pedido de Tomix, 20/10/2026). Antes solo recibía `pista`,
    el nombre del archivo."""
    link = link or checkout_de(nicho)
    que_muestra = ("El copy tiene que hablar de ESTE video: de lo que se ve y de lo que dice "
                   "la voz (abajo van la descripción, la lectura de venta y el guion).\n"
                   if (descripcion or guion) else f"El video muestra: {pista}.\n")
    p = (
        f"Escribí el copy de un posteo de Instagram/Facebook que VENDE un curso de "
        f"{tema_de(nicho)}. " + que_muestra +
        "  · Abre con UN emoji poco usado + pregunta que rompe una creencia\n"
        "  · 3-4 beneficios, uno por línea, cada uno con su emoji al inicio pegado\n"
        "  · Una línea que derribe la duda principal: no hace falta experiencia, se aprende "
        "paso a paso desde cero, a tu ritmo\n"
        f"  · Después, sola en su línea, la marca {MARCA_OFERTA} (ahí va el bloque de oferta "
        "fijo; no lo escribas vos)\n"
        f"  · Cierra con:\n👇 [llamado corto]\n🌐{link}\n\n⏳ [urgencia breve]\n\n"
        "REGLAS DURAS: español NEUTRO, PROHIBIDO el voseo (usá tú/puedes/aprende, nunca "
        "podés/aprendé). No inventes cifras exactas que no sepas. No menciones ningún "
        "sitio web fuera del enlace dado. Devolvé SOLO el copy, sin explicar nada."
    )
    # Datos verdaderos del curso (prompts/<nicho>_datos.txt): lo único que se puede
    # afirmar del producto en los beneficios.
    datos = config.prompt_de_nicho(nicho, "datos.txt", "")
    if datos:
        p += "\n\n" + datos
    if descripcion:
        p += "\n\nDESCRIPCIÓN Y LECTURA DE VENTA DEL VIDEO:\n" + descripcion[:5000]
    if guion:
        p += "\n\nGUION (lo que dice la voz):\n" + guion[:3000]
    r = _gemini(p, nicho)
    if not r or len(r.strip()) < 60:
        return None
    return con_bloque_oferta(r.strip(), nicho)


# El bloque de oferta lo pone el código, no Gemini: así sale siempre igual
# (texto de Tomix, 20/10/2026). Solo cambian las horas de video por nicho.
MARCA_OFERTA = "[BLOQUE_OFERTA]"
HORAS_VIDEO = {"bonsai": "+3,5",   # 3 h 41 min reales (Drive, 14/11)
               # 14/11: las páginas de estos cursos no dicen cuántas horas son. Vacío = la
               # línea sale sin número (antes heredaban el "+32" de hidroponía: dato falso).
               "herbologia": "", "terrarios": ""}


def bloque_oferta(nicho: str) -> str:
    horas = HORAS_VIDEO.get(nicho, "+32")
    primera = f"🎥| {horas} horas de video grabado\n" if horas else "🎥| Clases en video grabadas\n"
    return (primera +
            "📨| Acceso inmediato vía email\n"
            "🌐| 100% Online, sin horarios\n"
            "📥| Material Descargable\n"
            "💳| Pago único - Acceso de por vida\n"
            "🛡️| Garantía de prueba de 7 días\n"
            "🏅| Certificación de culminación")


_RE_OFERTA_VIEJA = re.compile(r"📘 ?Aprende más por menos:.*?acceso DE POR VIDA\.?", re.S)


# Invitación a comentar (28/10/2026): en Instagram el link del copy no se puede tocar y
# las tiendas de Meta no existen en Argentina. Quien comenta la palabra recibe el link
# por mensaje privado (lo hace el Worker: ver analisis/COMENTARIOS_IG.md). La palabra es
# la misma que dice la voz al cierre (prompts/<nicho>_voz_comun.txt). Tomix, 01/11: antes
# decía QUIERO para todos y no coincidía con el video.
PALABRA_COMENTARIO = {"hidroponia": "CULTIVO", "bonsai": "BONSAI",
                      "terrarios": "TERRARIO", "herbologia": "SANAR"}   # 14/11, Tomix
_RE_CTA_VIEJO = re.compile(r"\n*💬 Comenta \w+ y te mando el link por privado 📩[ \t]*")


def cta_comentario(nicho: str) -> str:
    return f"💬 Comenta {PALABRA_COMENTARIO.get(nicho, 'QUIERO')} y te mando el link por privado 📩"


def con_cta_comentario(copy: str, nicho: str) -> str:
    return _RE_CTA_VIEJO.sub("", copy).rstrip() + "\n\n" + cta_comentario(nicho)


def con_bloque_oferta(copy: str, nicho: str) -> str:
    """Pone el bloque fijo en la marca; si Gemini la omitió, reemplaza un bloque viejo
    o lo inserta antes del llamado final (👇). Siempre cierra con la invitación a
    comentar la palabra del nicho."""
    bloque = bloque_oferta(nicho)
    if MARCA_OFERTA in copy:
        return con_cta_comentario(copy.replace(MARCA_OFERTA, bloque), nicho)
    if _RE_OFERTA_VIEJA.search(copy):
        return con_cta_comentario(_RE_OFERTA_VIEJA.sub(bloque, copy), nicho)
    if "👇" in copy:
        i = copy.index("👇")
        return con_cta_comentario(copy[:i].rstrip() + "\n\n" + bloque + "\n\n" + copy[i:], nicho)
    return con_cta_comentario(copy + "\n\n" + bloque, nicho)


def latido(nombre: str, **campos) -> None:
    """Escribe state/<nombre>_heartbeat.json con pid+ts. El panel lo lee para pintar la
    cinta del pipeline: >3 min sin latido = 'sin señal' (amarillo), >10 = muerto (gris).
    Nunca debe romper al que lo llama: es telemetría, no lógica."""
    import json
    from datetime import datetime, timezone
    try:
        f = ROOT / "state" / f"{nombre}_heartbeat.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        campos.update(pid=os.getpid(), ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        f.write_text(json.dumps(campos, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


LOCK = ROOT / "state" / ".produciendo_stock"


def _tomar_lock() -> bool:
    """Un solo productor por vez. Dos a la vez se pisan el índice del stock en R2
    (leen-modifican-escriben sin bloqueo) y se pierde un reel: ya pasó. El candado
    caduca a los 40 min por si un proceso murió a mitad y lo dejó puesto."""
    import time
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        edad = time.time() - LOCK.stat().st_mtime
        if not _pid_vivo(_pid_del_lock()):
            # El dueño del candado murió (se cortó el proceso, se apagó la compu). Esperar
            # 40 minutos por un proceso que ya no existe es tiempo de producción tirado.
            log.warning("Candado huérfano (su proceso ya no está): lo piso.")
        elif edad < 2400:
            return False
        else:
            log.warning("Candado viejo (%.0f min): lo piso.", edad / 60)
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _pid_del_lock() -> int:
    try:
        return int(LOCK.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def _pid_vivo(pid: int) -> bool:
    """True si ese PID sigue corriendo. Ante la duda devuelve True: es preferible esperar
    de más a que dos productores se pisen el índice del stock y se pierda un reel."""
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20)
        return str(pid) in (r.stdout or "")
    except Exception:  # noqa: BLE001
        return True


def _soltar_lock() -> None:
    try:
        LOCK.unlink(missing_ok=True)
    except OSError:
        pass


def sintetizar_voz(guion: str, clave: str, niche, solo_charon: bool = False,
                   sin_voz_no_marca: bool = False):
    """Cascada de voz (orden de Tomix, invertido el 22/08/2026): Antonio -> Charon -> Antoni.

    Charon (Google AI Studio) muta de voz DENTRO de un mismo reel: sintetiza frase por
    frase (necesario para el timing real de los subtítulos) y cada llamada es una
    generación independiente sin semilla fija, así que el timbre no es estable entre
    frases. Se suma que el tier gratis de la API de TTS es de solo 10 pedidos por día
    POR CUENTA: un reel de 15-20 frases puede agotar una cuenta a mitad de camino y
    saltar a la siguiente en silencio, empeorando la mutación. Antonio (ElevenLabs)
    sintetiza el guion COMPLETO en una sola llamada: no tiene ese problema. Por eso pasa
    a ser la voz principal y Charon quedó de resguardo, solo si las 5 cuentas de
    ElevenLabs se quedaron sin cuota.

    Todas las cuentas (Google y Eleven) son de créditos GRATIS que se resetean solos:
    la cascada completa cuesta $0 — no hay que "cuidar" créditos de nadie.

    solo_charon=True: se salta Antonio y va directo a Charon (si tampoco puede, levanta
    CuotaAgotada). Nadie lo pide así hoy; queda para forzar la voz de Google a mano.
    sin_voz_no_marca=True: permite Antonio y Charon pero NUNCA cae a Antoni (que no es
    la voz de la marca). Para el re-doblaje del stock: sin apuro, mejor esperar la
    recarga de Antonio que sacar reels con otra voz."""
    from src import voiceover

    voces = carpeta_de("hidroponia") / "_VOCES"
    voces.mkdir(parents=True, exist_ok=True)
    # Voz gratuita de Microsoft fija por nicho (14/11, Tomix: terrarios = Dalia). Va en
    # niches/<nicho>.yaml como `voz_edge`. No gasta créditos de ElevenLabs.
    edge = voz_edge_de(niche)
    if edge:
        # Sin respaldo a ElevenLabs a propósito: gastaría créditos y le cambiaría la voz al
        # nicho. Si Microsoft falla, ese reel da error y se reintenta otro día.
        v, align = voz_edge(guion, edge, voces / f"voz_{clave}.mp3", _velocidad(niche))
        return v, align, f"Microsoft/{edge}"
    v = align = None
    usada = ""
    if not solo_charon:
        for i, k in enumerate(voiceover.eleven_keys(), 1):
            try:
                v, align = voiceover.synthesize_timed(
                    guion, k, niche.elevenlabs_voice, niche.elevenlabs_model,
                    voces / f"voz_{clave}.mp3", speed=_velocidad(niche), permitir_voz_gratis=False)
                usada = f"ElevenLabs/Antonio (cuenta {i})"
                break
            except voiceover.VozNoDisponible:
                continue
            except Exception as e:  # noqa: BLE001
                # Antes se tragaba el motivo: en GitHub las 5 cuentas fallaban sin decir por qué.
                log.warning("ElevenLabs cuenta %d falló: %s", i, str(e)[:160])
                continue
    # Orden (14/11, Tomix): Antonio (Confident Conversational Latino, solo anda en la
    # cuenta paga) -> Antoni (las 5 cuentas; también gasta caracteres) -> Charon al final.
    if solo_charon:
        raise CuotaAgotada("solo_charon ya no se usa: Charon va al final de la cascada")
    if v is None and sin_voz_no_marca:
        raise CuotaAgotada("Antonio sin cuota ahora; espero la próxima recarga "
                           "antes que usar una voz que no es de la marca")
    if v is None:
        # Antoni probando TODAS las cuentas. Antes probaba solo la última (keys[-1]),
        # que estaba agotada, mientras otras 3 cuentas tenían los 10.000 caracteres
        # libres: el 08 y 09/11 no salió ningún reel por eso.
        ultimo = None
        for i, k in enumerate(voiceover.eleven_keys(), 1):
            try:
                v, align = voiceover.synthesize_timed(
                    guion, k, niche.elevenlabs_voice, niche.elevenlabs_model,
                    voces / f"voz_{clave}.mp3", speed=_velocidad(niche), permitir_voz_gratis=True)
                usada = f"ElevenLabs/Antoni (cuenta {i})"
                break
            except Exception as e:  # noqa: BLE001
                ultimo = e
                log.warning("Antoni cuenta %d falló: %s", i, str(e)[:160])
        if v is None:
            # 14/11 (Tomix): Charon vuelve AL FINAL de la cascada. Antoni también gasta los
            # caracteres de cada cuenta, así que cuando las 5 se vacían no queda otra voz.
            # Mejor un reel con Charon que ningún reel.
            try:
                from src import voz_charon
                v, align = voz_charon.sintetizar_con_timing(guion, voces / f"voz_{clave}.wav")
                usada = "Google/Charon (último recurso)"
            except Exception as e:  # noqa: BLE001
                raise CuotaAgotada(f"Antonio, Antoni y Charon sin cuota ({str(ultimo)[:60]} / {str(e)[:60]})")
    return v, align, usada


def voz_edge_de(niche) -> str:
    """La voz de Microsoft fija del nicho (`voz_edge` en su yaml), o "" si usa ElevenLabs."""
    try:
        return str(config.read_niche_raw(niche.name).get("voz_edge") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def voz_edge(guion: str, voz: str, destino: Path, velocidad: float = 1.0):
    """Voz gratuita de Microsoft (edge-tts). Devuelve (mp3, alignment) con el MISMO formato
    que ElevenLabs (tiempo de cada carácter), que es lo que usan los subtítulos."""
    import asyncio
    import edge_tts
    palabras = []

    async def correr():
        com = edge_tts.Communicate(guion, voz, rate=f"{round((velocidad - 1) * 100):+d}%",
                                   boundary="WordBoundary")
        with open(destino, "wb") as f:
            async for ch in com.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":
                    ini = ch["offset"] / 1e7
                    palabras.append((ch["text"], ini, ini + ch["duration"] / 1e7))
    asyncio.run(correr())
    if not palabras:
        raise RuntimeError(f"edge-tts no devolvió audio con {voz}")
    chars, t0, t1 = [], [], []
    for i, (txt, a, b) in enumerate(palabras):
        if i:
            chars.append(" "); t0.append(palabras[i - 1][2]); t1.append(a)
        paso = (b - a) / max(1, len(txt))
        for j, c in enumerate(txt):
            chars.append(c); t0.append(a + j * paso); t1.append(a + (j + 1) * paso)
    log.info("Voz %s guardada -> %s (%d palabras, %.1f s)", voz, destino.name, len(palabras), t1[-1])
    return destino, {"characters": chars, "character_start_times_seconds": t0,
                     "character_end_times_seconds": t1}


def _audio_con_voz(video: Path) -> bool:
    """¿Hay alguien HABLANDO en el audio de este video? Muestrea el inicio y la
    mitad (15s cada uno) y le pregunta a Gemini. Si no se puede determinar
    (sin cuota, error), responde que SÍ: eso hace que el render reemplace el
    audio en vez de mezclarlo, que es el único resultado seguro."""
    import tempfile
    from google import genai
    from google.genai import types
    from src import videoedit

    dur = videoedit.probe_duration(video)
    ventanas = [1.0] + ([max(1.0, dur / 2 - 7)] if dur > 32 else [])
    for ini in ventanas:
        tmp = Path(tempfile.gettempdir()) / f"vozchk_{video.stem}_{int(ini)}.mp3"
        p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.1f}",
                            "-t", "15", "-i", str(video), "-vn", "-b:a", "48k",
                            str(tmp)], capture_output=True)
        if p.returncode != 0 or not tmp.exists():
            return True
        parte = types.Part.from_bytes(data=tmp.read_bytes(), mime_type="audio/mp3")
        veredicto = None
        for n in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3",
                  "GEMINI_API_KEY_4", "GEMINI_API_KEY_5"):
            k = (os.getenv(n) or "").strip()
            if not k:
                continue
            cli = genai.Client(api_key=k)
            for modelo in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-3.6-flash"):
                try:
                    r = cli.models.generate_content(
                        model=modelo,
                        contents=["¿Hay una PERSONA hablando (narrando, explicando) en "
                                  "este audio? Música o sonidos ambiente NO cuentan. "
                                  "Responde SOLO una palabra: SI o NO.", parte])
                    if r.text:
                        veredicto = r.text.strip().upper()
                        break
                except Exception:  # noqa: BLE001
                    continue
            if veredicto:
                break
        if veredicto is None or not veredicto.startswith("NO"):
            return True
    return False


def renderizar_reel(nicho: str, clave: str, mp4: Path, guion: str, niche,
                    solo_charon: bool = False,
                    sin_voz_no_marca: bool = False,
                    mutear: bool = False) -> tuple[Path, str]:
    """Video fuente + guion -> publicar.mp4 con voz, subs, mockup y logo.
    Devuelve (ruta_final, voz_usada). Todo local salvo la síntesis de voz."""
    from src import videoedit, subtitles

    v, align, usada = sintetizar_voz(guion, clave, niche, solo_charon=solo_charon,
                                     sin_voz_no_marca=sin_voz_no_marca)
    v = Path(v)
    # Normalizada para que no suba y baje sola entre frases (Charon las genera de a una).
    norm = v.with_name("norm_" + v.name)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(v), "-af",
                    "dynaudnorm=f=250:g=15:p=0.9:m=8,loudnorm=I=-16:TP=-1.5:LRA=11",
                    str(norm)], capture_output=True)
    if norm.exists():
        v = norm

    out = ROOT / "output" / nicho / clave
    out.mkdir(parents=True, exist_ok=True)
    final = mp4
    vdur, cur = videoedit.probe_duration(v), videoedit.probe_duration(mp4)
    target = vdur + 2.5
    if cur > target + 1.5:
        # recorte que CONSERVA el audio ambiente (trim_to_duration lleva -an y lo mata)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(final), "-t", f"{target:.3f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                        "-c:a", "aac", "-b:a", "192k", str(out / "recortado.mp4")], check=True)
        final = out / "recortado.mp4"
    elif vdur + 0.4 > cur:
        final = videoedit.extend_to_duration(final, vdur + 0.4, out / "extendido.mp4")

    # Mezclar el audio original SOLO si es ambiente de verdad (nadie hablando).
    # Dos fuentes "ASMR" (stk-bonsa-681478 y -954144) tenían narración en inglés
    # y quedó sonando de fondo abajo de la voz en español. Si el chequeo no se
    # puede hacer, se REEMPLAZA: perder ambiente es barato, publicar inglés no
    # tiene arreglo.
    final = (videoedit.mix_voice_over(final, v, out / "con_voz.mp4", AMBIENTE)
             if not mutear and videoedit.has_audio(final) and not _audio_con_voz(final)
             else videoedit.replace_audio(final, v, out / "con_voz.mp4"))
    # BUG (09/09): esto nunca pasaba la config del nicho -- quemaba SIEMPRE Arial
    # Black 92 sin importar lo que se cambiara en el panel (Subtítulos). El otro
    # camino de producción (src/pipeline._process_media) ya lo hacía bien; acá
    # faltaba. Confirmado con Tomix: cambiaba fuente/tamaño y no se notaba nada.
    ass = subtitles.construir_ass(
        align, out / "subs.ass",
        font=niche.subtitle_font, font_size=niche.subtitle_font_size,
        outline=niche.subtitle_outline, margin_v=niche.subtitle_margin_v,
        karaoke=niche.subtitle_karaoke, popin=niche.subtitle_popin,
        colores=niche.subtitle_colores, emojis=niche.subtitle_emojis,
        emoji_map=niche.subtitle_emoji_map,
        palabras_por_grupo=niche.subtitle_palabras, color=niche.subtitle_color,
        minusculas=niche.subtitle_minusculas)
    if ass:
        # 23/11 (Tomix): si el original trae subtítulos quemados (p. ej. en inglés), una
        # cinta borrosa los tapa y los nuestros van encima. Gemini mira el video fuente.
        cinta = None
        try:
            from src import texto_quemado
            cinta = texto_quemado.cinta_para(mp4, niche)
        except Exception as e:  # noqa: BLE001
            print(f"  cinta: no pude revisar el video ({str(e)[:100]}); sin cinta", flush=True)
        final = videoedit.burn_subtitles(final, ass, out / "con_subs.mp4", cinta=cinta)
    mk = ROOT / niche.mockup_file
    lg = ROOT / niche.logo_file
    if niche.add_mockup and mk.exists():
        # MOCKUP GRANDE (19/10/2026): ocupa el espacio libre entre el logo y los
        # subtítulos, sin deformar. "Tamaño" del panel = fracción de ese máximo (1 = lo
        # más grande que entra sin tapar nada). Se le recorta el borde transparente para
        # que el producto se vea grande de verdad.
        from PIL import Image
        w, h = videoedit.probe_dimensions(final)
        arriba, abajo = _zona_mockup(niche, w, h, lg)
        img = Image.open(mk).convert("RGBA")
        caja = img.getbbox()
        if caja:
            img = img.crop(caja)
        recortado = out / "mockup_recortado.png"
        img.save(recortado)
        iw, ih = img.size
        f = min(w * 0.95 / iw, max(1, abajo - arriba) / ih) * max(0.1, min(1.2, float(niche.mockup_scale or 1.0)))
        ancho = max(2, int(iw * f) // 2 * 2)
        alto = int(ih * f)
        y = int(arriba + (abajo - arriba - alto) / 2)
        final = videoedit.overlay_last_secs(final, recortado, niche.mockup_seconds,
                                            out / "final.mp4", ancho_px=ancho, y_px=y)
    if niche.add_logo and lg.exists():
        final = videoedit.overlay_logo(final, lg, out / "con_logo.mp4",
                                       niche.logo_scale, niche.logo_position)
    final = videoedit.normalize_for_publish(final, out / "publicar.mp4")
    return final, usada


def producir(nicho: str, cuantos: int = 3, clase: str = "AUTO") -> tuple[list, list]:
    """Devuelve (hechos, errores). Cada 'hecho' ya quedó subido al stock en R2."""
    from src import toggles
    if not toggles.activo(nicho, "produccion"):
        return ([], [f"producción de {nicho} apagada (interruptor del panel)"])
    if not _tomar_lock():
        return ([], ["ya hay otra producción en curso; probá en un rato"])
    try:
        return _producir(nicho, cuantos, clase=clase)
    finally:
        _soltar_lock()


def _producir(nicho: str, cuantos: int = 3, clase: str = "AUTO") -> tuple[list, list]:
    config.read_env()
    import armar_stock
    import registro_fuentes

    # Un nicho a medio configurar no se rompe: se dice POR QUÉ no puede producir. Sin
    # esto, uno sin link de venta llegaba hasta el copy y publicaba "PENDIENTE" de link.
    listo, motivo = config.nicho_produce(nicho)
    if not listo:
        return ([], [f"{nicho} no puede producir todavía: {motivo}"])

    niche = config.load_niche(nicho)
    # Reservas (02/11/2026): se eligen unas fuentes de más y se corta al llegar a
    # `cuantos`. Antes, si Gemini fallaba con un video (respuesta vacía, 503...), ese reel
    # se perdía ese día: hidroponía quedó con la mitad de stock que bonsái por eso.
    pedidos = cuantos
    cuantos = cuantos + RESERVAS
    try:
        fuentes_a_demanda(nicho, cuantos)
    except Exception as e:  # noqa: BLE001 — buscar fuentes nuevas no puede voltear la tanda
        log.warning("Fuentes a demanda de %s falló: %s", nicho, str(e)[:120])
    # AUTO (20/10/2026, decisión de Tomix): primero los MUDOS (ASMR), con guion inventado
    # por Gemini con la fórmula ganadora. Solo si no quedan mudos se completa con
    # hablados (doblaje).
    if clase == "AUTO":
        fuentes = [(p, "ASMR") for p in elegir_fuentes(nicho, cuantos, clase="ASMR")]
        if len(fuentes) < cuantos:
            fuentes += [(p, "TRADUCIR") for p in elegir_fuentes(nicho, cuantos - len(fuentes), clase="TRADUCIR")]
        for modo in (() if nicho in VARIAR_CREADORES else ("MUTEADO", "REPETIR")):
            if len(fuentes) < cuantos:
                ya = {f for f, _ in fuentes}      # el mismo archivo no sale dos veces por tanda
                fuentes += [(p, modo) for p in elegir_reuso(nicho, cuantos - len(fuentes), modo)
                            if p not in ya]
    else:
        fuentes = [(p, clase) for p in elegir_fuentes(nicho, cuantos, clase=clase)]
    if not fuentes:
        return ([], [f"no quedan fuentes {clase} verificadas sin usar de {nicho}"])

    hechos, errores = [], []
    for mp4, clase in fuentes:
        if len(hechos) >= pedidos:
            break       # las reservas que sobran quedan sin usar para la próxima
        tid = (re.search(r"__(\d+)", mp4.name) or [None, ""])[1]
        clave = f"stk-{nicho[:5]}-{tid[-6:]}"
        # Muteados y repeticiones llevan sufijo: con la misma clave PISARÍAN el reel
        # original en el stock (agregar() reemplaza por id).
        if clase == "MUTEADO":
            clave += "-m"
        elif clase == "REPETIR":
            clave += f"-r{len(_usos_de(nicho).get(tid, [])) + 1}"
        try:
            latido("productor", corriendo=True, etapa="produciendo", nicho=nicho,
                   video_actual=clave, hechos=len(hechos))
            pista = re.sub(r"__\d+.*", "", mp4.name).replace("-", " ") or nicho
            out = ROOT / "output" / nicho / clave
            # Guion por el camino OFICIAL: Gemini mira el video, prompts/ manda.
            # Muteado y repetición: guion NUEVO sobre lo que se VE (modo describe, como un
            # ASMR). Un solo camino (02/11): la repetición usa el mismo texto que los nuevos.
            guion = guion_del_pipeline(nicho, niche, clave, mp4, out,
                                       clase="ASMR" if clase in ("MUTEADO", "REPETIR") else clase)
            desc_f = out / "descripcion_gemini.txt"
            desc = desc_f.read_text(encoding="utf-8", errors="ignore") if desc_f.is_file() else ""
            desc = re.split(r"===\s*DESCRIPCIÓN DEL VIDEO", desc, maxsplit=1)[-1] if desc else ""
            copy = copy_posteo(nicho, pista, link=getattr(niche, "cta_link", "") or "",
                               descripcion=desc, guion=guion or "")
            if not guion or not copy:
                errores.append(f"{clave}: Gemini no devolvió guion o copy")
                continue

            final, usada = renderizar_reel(nicho, clave, mp4, guion, niche,
                                           mutear=clase in ("MUTEADO", "TRADUCIR"))

            # El panel "Generados" y el publisher leen copy_final.txt del output local.
            # El stock guardaba el copy SOLO en el index de R2: la interfaz mostraba
            # "(sin copy)" y "Publicar ahora" desde ahí salía sin texto.
            (out / "copy_final.txt").write_text(copy, encoding="utf-8")

            # Se guarda la ficha del reel: voz, guion y si el guion es INVENTADO (el video
            # venía mudo) o una TRADUCCIÓN. Es lo que Eugenia informa al publicar.
            tipo = {"TRADUCIR": "traduccion", "MUTEADO": "muteado_guion_nuevo",
                    "REPETIR": "repeticion_otro_angulo"}.get(clase, "guion_nuevo_asmr")
            # PORTADA (08/11/2026): la IA elige del video TERMINADO el cuadro más llamativo, cuando el
            # subtítulo dice una palabra clave. Instagram la usa por `thumb_offset`, Facebook por el jpg.
            portada_extras = {}
            try:
                from src import portada as _portada
                pt = _portada.elegir(final, nicho)
                if pt:
                    jpg = out / "portada.jpg"
                    jpg.write_bytes(pt["jpg"])
                    if armar_stock.r2_put(jpg, f"{armar_stock.BUCKET}/reels/{clave}_portada.jpg", "image/jpeg"):
                        portada_extras = {"portada_ms": pt["ms"], "portada_palabra": pt["palabra"],
                                          "portada_key": f"reels/{clave}_portada.jpg"}
            except Exception as e:  # noqa: BLE001
                log.warning("Portada: %s", str(e)[:100])
            armar_stock.agregar(nicho, clave, final, copy, pista[:40],
                                voz=usada, guion=guion, tipo=tipo,
                                extras={"arreglado": True, "descripcion": (desc or "")[:8000],
                                        "fuente": tid, "clase": clase, **portada_extras})
            prefijo = {"MUTEADO": "muteado: ", "REPETIR": "repite: "}.get(clase, "")
            registro_fuentes.registrar(nicho, clave, tid, (prefijo + pista)[:60])
            hechos.append(clave)
            log.info("Stock +1: %s (%s)", clave, nicho)
        except CuotaAgotada:
            # No tiene sentido seguir con las otras fuentes: el límite es de la cuenta,
            # no de este video. Se corta y se avisa con una marca que el productor
            # diario reconoce para dormir y volver a intentar.
            errores.append(f"{clave}: CUOTA")
            log.warning("Gemini en límite: corto la tanda y espero.")
            break
        except Exception as e:  # noqa: BLE001
            if _es_cuota(e):
                errores.append(f"{clave}: CUOTA")
                log.warning("Cuota agotada (%s): corto la tanda.", str(e)[:80])
                break
            errores.append(f"{clave}: {str(e)[:90]}")
            log.warning("Falló %s: %s", clave, str(e)[:120])
            # 3 fallos AL MISMO video -> se descarta para siempre (09/09). Sin esto,
            # una fuente que Gemini nunca puede procesar (archivo roto, etc.) queda
            # SIEMPRE primera en la lista sin usar y se reintenta en cada vuelta, para
            # siempre -- confirmado con stk-bonsa-692321: fallaba cada ~6 min, sin
            # parar, corriendo de fondo el día entero.
            if tid and _tercer_fallo(tid):
                log.warning("%s falló 3 veces: la descarto para siempre.", tid)
                try:
                    registro_fuentes.registrar(nicho, clave, tid, "descartada: Gemini no la procesa")
                except Exception:  # noqa: BLE001
                    pass
    return hechos, errores


def main() -> int:
    ap = argparse.ArgumentParser()
    # Los nichos salen de config (fuente única), así uno nuevo se puede producir apenas
    # queda configurado. Se suman los que tienen carpeta propia acá para no rechazar por
    # línea de comandos a uno que hoy produce y quedó con el YAML a medias.
    ap.add_argument("--nicho", default="bonsai",
                    choices=sorted(set(config.nichos_produccion()) | set(CARPETA)))
    ap.add_argument("--cantidad", type=int, default=3)
    ap.add_argument("--clase", default="AUTO", choices=["AUTO", "ASMR", "TRADUCIR"],
                    help="ASMR = mudo, se inventa guion; TRADUCIR = habla en otro "
                         "idioma, se traduce y se reemplaza el audio")
    ap.add_argument("--listar", action="store_true")
    a = ap.parse_args()

    if a.listar:
        import armar_stock
        idx = armar_stock.leer_index()
        log.info("Stock: %d reels", len(idx))
        for x in idx:
            marca = "✔" if x.get("arreglado") else "✗ (guion viejo)"
            log.info("  %-22s %-10s %s %s", x["id"], x["nicho"], x.get("creado", ""), marca)
        return 0

    hechos, errores = producir(a.nicho, a.cantidad, clase=a.clase)
    log.info("Hechos: %d %s | errores: %d", len(hechos), hechos, len(errores))
    for e in errores:
        log.info("  · %s", e)
    return 0 if hechos or not errores else 1


if __name__ == "__main__":
    raise SystemExit(main())
