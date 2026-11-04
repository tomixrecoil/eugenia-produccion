"""
Lógica de audio con Gemini:
  - classify_audio: detecta si hay voz hablada y en qué idioma.
  - spanish_script: genera el guión en español para la voz de ElevenLabs,
        ya sea describiendo lo visual (video mudo) o doblando el inglés.
"""
from __future__ import annotations

import json
import re

from src import gemini_client
from src.gemini_client import get_client
from src.logging_setup import get_logger

log = get_logger()

# ~2.7 palabras por segundo es un ritmo de narración natural en español.
WORDS_PER_SEC = 2.7


def _client(api_key: str):
    return get_client(api_key)


def _text(resp) -> str:
    return (resp.text or "").strip()


def classify_audio(transcription: str, api_key: str, model: str) -> dict:
    """Devuelve {'has_speech': bool, 'language': 'es'|'en'|'other'|'none'}.

    PRIMERO se busca la línea "IDIOMA DEL AUDIO: xx" que declara el análisis del video.
    Es la fuente confiable: el prompt de análisis está escrito en español y Gemini
    tendía a DEVOLVER LA TRANSCRIPCIÓN YA TRADUCIDA. Al deducir el idioma del texto
    traducido, un video en inglés se clasificaba como español, se saltaba el doblaje
    y se publicaba con el audio original en inglés.
    """
    m_idioma = re.search(r"IDIOMA DEL AUDIO\s*:\s*([a-zA-Z]{2,6})", transcription or "")
    if m_idioma:
        lang = m_idioma.group(1).lower()
        if lang in ("es", "en", "pt", "other", "none"):
            if lang in ("pt",):
                lang = "other"
            resultado = {"has_speech": lang != "none", "language": lang}
            log.info("Idioma declarado por el análisis: %s", resultado)
            return resultado

    prompt = (
        "Analizá esta transcripción de audio de un video. Determiná si hay narración "
        "hablada (voz de una persona) y en qué idioma. Si solo hay música, ruido o está "
        "vacía, no hay habla.\n\n"
        "Respondé SOLO con JSON válido, sin texto extra, con este formato exacto:\n"
        '{\"has_speech\": true/false, \"language\": \"es\"|\"en\"|\"other\"|\"none\"}\n\n'
        f"TRANSCRIPCIÓN:\n{transcription[:4000]}"
    )
    resp = gemini_client.run(lambda c: gemini_client.generate(c, model, [prompt]))
    raw = _text(resp)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"has_speech": False, "language": "none"}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"has_speech": False, "language": "none"}
    lang = str(data.get("language", "none")).lower()
    if lang not in ("es", "en", "other", "none"):
        lang = "other"
    result = {"has_speech": bool(data.get("has_speech", False)), "language": lang}
    log.info("Audio detectado: %s", result)
    return result


# Valores por defecto de los prompts de voz. Se pueden editar desde la app; estos
# quedan como respaldo si falta el archivo en prompts/.
_VOZ_DESCRIBE = (
    "El video NO tiene narración. Escribí una voz en off en español latino neutro, "
    "con tono experto, cercano y aspiracional, que describa y venda lo que se muestra. "
    "SEGUÍ ESTA ESTRUCTURA GANADORA (es la que más convierte, respetala paso a paso):\n"
    "1) ABRÍ con una pregunta que haga IMAGINAR el resultado soñado en su propia casa "
    "(ej: '¿Te imaginas cosechar alimentos frescos y gigantes en tu hogar?').\n"
    "2) Aclará ENSEGUIDA que es sorprendentemente FÁCIL / más sencillo de lo que imagina "
    "(mata la objeción de 'es complicado, yo no puedo').\n"
    "3) Narrá el PROCESO paso a paso que se ve en el video (germinación, ensamblar los "
    "módulos, la bomba, el riego automatizado, trasplantar) para que se sienta alcanzable "
    "y coincida con la imagen.\n"
    "4) Usá adjetivos sensoriales y de impacto: frescos, limpios, gigantes, abundantes, "
    "crecimiento acelerado, raíces sanas, libres de tierra, sin plagas.\n"
    "5) CERRÁ con una frase de TRANSFORMACIÓN o estilo de vida, NO de venta dura "
    "(ej: 'Da el paso hacia una vida más sana', 'lleva tu huerto al siguiente nivel').\n"
    "Basate en esta descripción cuadro a cuadro del video:"
)
_VOZ_TRADUCIR = (
    "Doblá al español latino neutro la siguiente narración (está en otro idioma). "
    "Mantené el sentido, el orden y el ritmo para que coincida con la imagen. "
    "Narración original:"
)


_RE_MARCA_TIEMPO = re.compile(
    r"\[?\s*\d{1,2}:\d{2}(?:\.\d+)?\s*[-–—]\s*\d{1,2}:\d{2}(?:\.\d+)?\s*\]?\s*:?\s*")


def sin_marcas(texto: str) -> str:
    """Saca las marcas de tiempo ([00:00 - 00:09]) en CUALQUIER lugar del texto. El filtro
    viejo (^\\[\\d.:\\s-]+\\]) estaba mal escrito y no las agarraba: en un guion de bonsái
    se leyeron en voz alta y salieron en los subtítulos (20/10/2026)."""
    t = _RE_MARCA_TIEMPO.sub(" ", texto or "")
    t = re.sub(r"[ \t]{2,}", " ", t)
    return re.sub(r" *\n *", "\n", t).strip()


def vende_en_voz(video_id: str) -> bool:
    """Si ESTE video nombra el curso en la voz (True) o es contenido puro y la venta va en
    el copy (False). Mitad y mitad, fijo por video (se puede re-correr sin que cambie).
    Así funcionaron los ganadores: unos venden en la voz, otros solo dan el 'wow'."""
    if not video_id:
        return True
    return sum(ord(c) for c in str(video_id)) % 2 == 0


def formato_sugerido(video_id: str, formatos: str) -> str:
    """El nombre del formato que le toca a este video si varios encajan igual. Los
    formatos van en prompts/<nicho>_formatos.txt separados por una línea '---'; el
    nombre es la primera línea de cada bloque. Rota por video para no repetir."""
    bloques = [b.strip() for b in re.split(r"(?m)^\s*---\s*$", formatos or "") if b.strip()]
    if not bloques:
        return ""
    elegido = bloques[(sum(ord(c) for c in str(video_id or "x")) // 2) % len(bloques)]
    return elegido.splitlines()[0].strip()


def spanish_script(mode: str, source_text: str, duration_secs: float,
                   api_key: str, model: str,
                   video_id: str = "", nicho: str = "", palabras: int | None = None,
                   velocidad: float = 1.0) -> str:
    """mode='describe' (video mudo) o 'translate' (doblar inglés).

    Un solo camino (02/11): la fórmula de prompts/voz_describe.txt para los mudos y
    voz_traducir.txt para los hablados, con el piso común de prompts/voz_comun.txt
    (reglas anti-IA, español neutro y el cierre con CTA).
    """
    words = max(12, int(duration_secs * WORDS_PER_SEC))
    # `palabras` (19/10/2026): quien llama ya sabe cuántas entran de verdad (duración del
    # video x ritmo real de la voz x velocidad del panel). Manda sobre la estimación.
    if palabras:
        words = max(12, int(palabras))

    # Los prompts se pueden editar desde la app (pestaña Prompts). Si el archivo
    # no existe, se usa el texto de acá: nunca se rompe por un archivo faltante.
    # Se busca primero el del NICHO (prompts/<nicho>_voz_*.txt) y si no lo tiene se usa
    # el compartido: el contenido actual es de hidroponía (germinación, la bomba, el
    # riego automatizado, "Comenta CULTIVO") y sin esto un reel de bonsái recibiría un
    # guion hablando de riego.
    import config
    if mode != "describe":
        task = config.prompt_de_nicho(nicho, "voz_traducir.txt", _VOZ_TRADUCIR)
    else:
        task = config.prompt_de_nicho(nicho, "voz_describe.txt", _VOZ_DESCRIBE)

    comun = config.prompt_de_nicho(nicho, "voz_comun.txt", "")
    # Fórmula ganadora (19/10/2026, ver analisis/GANADORES_IG_2026-10.md): formatos que
    # funcionaron, si este video nombra el curso, y los datos verdaderos del curso. Los
    # tres viven en prompts/ por nicho; un nicho sin esos archivos sale igual que antes.
    formatos = config.prompt_de_nicho(nicho, "formatos.txt", "")
    datos = config.prompt_de_nicho(nicho, "datos.txt", "")
    task = (task.replace("{FORMATOS}", formatos)
                .replace("{FORMATO_SUGERIDO}", formato_sugerido(video_id, formatos)))
    # Palabras por cada parte de 9 s (3 tramos de 3 s de la descripción): así lo que se
    # escucha va con lo que se ve. Sale de las palabras totales y la duración del video.
    p9 = max(6, round(words * 9 / max(duration_secs, 9))) if palabras else round(9 * WORDS_PER_SEC)
    task = task.replace("{PALABRAS_9S}", str(p9))
    comun = comun.replace("{VENDE}", (
        "SÍ — en este video nombra el curso con UNA o dos frases antes del cierre (qué "
        "aprende la persona y que es para principiantes), usando solo DATOS VERDADEROS DEL CURSO."
        if vende_en_voz(video_id) else
        "NO — en este video NO nombres el curso: es contenido puro, la venta va en el texto "
        "de la publicación. Solo el cierre obligatorio."))

    prompt = (
        f"{task}\n\n{source_text[:6000]}\n\n"
        f"{comun}\n\n"
        f"{datos}\n\n"
        "REGLAS ESTRICTAS:\n"
        + (f"- DURACIÓN DEL VIDEO: {duration_secs:.0f} segundos. La voz va a velocidad "
           f"x{velocidad:g}, así que entran aprox. {words} palabras. La narración tiene que "
           "cubrir el video COMPLETO, de principio a fin: ni se queda corta ni se pasa.\n"
           if palabras else
           f"- Duración objetivo: ~{duration_secs:.0f} segundos (aprox. {words} palabras). "
           "No te pases; es mejor un poco más corto que más largo.\n") +
        "- Devuelve SOLO el texto para leer en voz alta: sin timestamps, sin acotaciones, "
        "sin comillas, sin viñetas, sin emojis. Solo las frases corridas.\n"
    )
    # Referencia de los reels ganadores del nicho como instrucción de sistema (todas las
    # cuentas la reciben en cada pedido; ver src/referencia.py).
    from src import referencia
    sistema_ref = referencia.como_sistema(nicho)
    resp = gemini_client.run(lambda c: gemini_client.generate(c, model, [prompt], system=sistema_ref))
    script = _text(resp)
    # Limpieza defensiva de posibles restos de formato.
    script = sin_marcas(script)
    # LARGO (19/10/2026): si se pasa más de un 15% de lo pedido, la voz queda más larga
    # que el video y se congela el último cuadro (pasó: 24 s de imagen quieta en un
    # doblaje de 70 s). Se pide UNA vez que lo acorte, conservando datos y cierre.
    if len(script.split()) > words * 1.15:
        acortar = (
            f"Acorta este guion a {words} palabras como máximo. Conserva el gancho, los datos "
            "concretos más fuertes y la ÚLTIMA frase textual (el cierre). Quita lo que menos "
            "aporta. Mismo idioma y mismo tono. Devuelve SOLO el texto final.\n\n" + script)
        try:
            r2 = gemini_client.run(lambda c: gemini_client.generate(c, model, [acortar], system=sistema_ref))
            corto = sin_marcas(_text(r2))
            if corto and len(corto.split()) < len(script.split()):
                log.info("Guion acortado: %d -> %d palabras (pedido %d).",
                         len(script.split()), len(corto.split()), words)
                script = corto
        except Exception as e:  # noqa: BLE001
            log.warning("No pude acortar el guion (%s); queda el largo.", str(e)[:80])
    log.info("Guión %s generado (%d palabras).", mode, len(script.split()))
    return script
