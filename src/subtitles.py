"""
Subtítulos quemados en el video, sincronizados con la voz.

No hace falta transcribir: ElevenLabs devuelve el tiempo EXACTO de cada carácter
(`synthesize_timed`), así que el timing es perfecto por construcción.

  alignment (chars + tiempos) -> palabras -> grupos de 2-3 -> archivo .ass -> ffmpeg
"""
from __future__ import annotations

from pathlib import Path

from src.logging_setup import get_logger

log = get_logger()

# Estilo "reel viral": pocas palabras, grandes, blancas con borde negro grueso.
# La franja de abajo de Instagram la tapan el caption y los botones -> el texto va
# más arriba (MarginV alto sobre 1920 de alto).
PLAY_W, PLAY_H = 1080, 1920
FONT = "Arial Black"
FONT_SIZE = 92
MARGIN_V = 520          # distancia desde abajo: queda ~a 2/3 de alto, zona segura
OUTLINE = 7             # borde negro grueso: legible sobre cualquier fondo
PALABRAS_POR_GRUPO = 3

# Ancho promedio de una letra como fracción del tamaño de fuente. Sirve para achicar
# una palabra sola que no entra en el ancho útil (modo 1 palabra con letra gigante).
# Medido 02/11/2026: "utilizando" en Baloo 2 ExtraBold 234 -> 670 px (0,29), pero las
# palabras con m/p/d anchas ("completamente") pasan de 0,33: se usa 0,34 con margen.
ANCHO_LETRA = {"Baloo 2 ExtraBold": 0.34}
ANCHO_LETRA_DEFAULT = 0.57   # Arial Black (52 px por letra a 92)
ANCHO_UTIL = 900             # 1080 menos 90 de margen a cada lado (borde incluido)
SIGNOS = ".,;:!?¡¿\"'«»()…"


def palabras_de_alignment(alignment: dict) -> list[tuple[str, float, float]]:
    """Convierte el timing por carácter en [(palabra, inicio, fin), ...]."""
    chars = alignment.get("characters") or []
    ini = alignment.get("character_start_times_seconds") or []
    fin = alignment.get("character_end_times_seconds") or []
    if not chars or len(chars) != len(ini) or len(chars) != len(fin):
        return []
    palabras, buf, t0, t1 = [], "", None, None
    for c, a, b in zip(chars, ini, fin):
        if c.isspace():
            if buf:
                palabras.append((buf, t0, t1))
                buf, t0, t1 = "", None, None
            continue
        if not buf:
            t0 = a
        buf += c
        t1 = b
    if buf:
        palabras.append((buf, t0, t1))
    return palabras


# Ancho útil en caracteres. Con Arial Black 92 sobre 1080 de ancho y 60px de margen a
# cada lado quedan 960px, y cada carácter mide ~52px de promedio: ~18 caracteres entran.
# Se dejan 16 de margen de seguridad porque las mayúsculas y las "m/w" son más anchas.
MAX_CHARS_LINEA = 16


def _agrupar(palabras: list[tuple[str, float, float]],
             por_grupo: int = PALABRAS_POR_GRUPO,
             max_chars: int = MAX_CHARS_LINEA) -> list[list[tuple[str, float, float]]]:
    """Junta las palabras en bloques cortos, que es como se leen los reels.

    Corta por PALABRAS **y también por ANCHO**. Antes agrupaba de a 3 palabras a secas
    y con palabras largas el renglón se salía de la pantalla: se vio publicado
    "sencillamente fantástico! Es" con la primera y la última letra cortadas contra el
    borde. Una palabra sola más larga que el máximo se deja igual (no se puede partir
    sin que quede peor), pero no se le suma ninguna otra.

    Devuelve la lista de palabras de CADA grupo (no el texto ya unido): los efectos
    creativos (karaoke, colores) necesitan el timing y el texto de cada palabra por
    separado, no solo el del grupo entero."""
    grupos: list[list[tuple[str, float, float]]] = []
    actual: list[tuple[str, float, float]] = []

    def _cerrar():
        if actual:
            grupos.append(list(actual))
            actual.clear()

    for p in palabras:
        largo_con = len(" ".join(q[0] for q in actual + [p]))
        if actual and (len(actual) >= por_grupo or largo_con > max_chars):
            _cerrar()
        actual.append(p)
    _cerrar()
    return grupos


def _ts(segundos: float) -> str:
    """Formato de tiempo de ASS: h:mm:ss.cc"""
    if segundos < 0:
        segundos = 0.0
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = segundos % 60
    return f"{h}:{m:02d}:{s:05.2f}"


# ---------------------------------------------------------------------------
# SUBTÍTULOS "CREATIVOS" (09/09, a pedido de Tomix) — 4 interruptores
# independientes, se pueden combinar todos, ninguno, o algunos:
#   karaoke  -> cada palabra pasa de blanco a un color al momento exacto de decirse
#   popin    -> cada grupo entra con un rebote de escala (chico -> grande -> normal)
#   colores  -> paleta rotativa por palabra en vez de blanco monocromo
#   emojis   -> si alguna palabra del grupo matchea el mapa, se le pega un emoji
# Colores ASS van en formato &HBBGGRR& (orden BGR, al revés del RGB de toda la vida).
# ---------------------------------------------------------------------------
PALETA_COLORES = ["&H00FFFF&", "&HFFFF00&", "&H9314FF&", "&H008CFF&", "&H32FF32&"]
COLOR_BLANCO = "&HFFFFFF&"
COLOR_KARAOKE_DEFAULT = "&H00FFFF&"   # amarillo, si "colores" está apagado


def _normalizar_palabra(p: str) -> str:
    """Para matchear contra el mapa de emojis: minúscula y sin puntuación pegada
    ("planta." o "¡plantas" tienen que matchear "planta"/"plantas" igual)."""
    return p.strip(".,!?¡¿:;\"'()").lower()


def parsear_emoji_map(texto: str) -> dict[str, str]:
    """"palabra=emoji" por línea -> dict. Líneas vacías o sin '=' se ignoran, nunca
    rompen el render — un mapa mal editado a mano no puede tirar abajo la producción."""
    out = {}
    for linea in (texto or "").splitlines():
        linea = linea.strip()
        if not linea or "=" not in linea:
            continue
        palabra, _, emoji = linea.partition("=")
        palabra, emoji = palabra.strip().lower(), emoji.strip()
        if palabra and emoji:
            out[palabra] = emoji
    return out


def _texto_grupo(grupo: list[tuple[str, float, float]], a0: float,
                 karaoke: bool, colores: bool, emojis: bool,
                 emoji_map: dict[str, str]) -> str:
    """Arma el texto (con overrides ASS inline) de UN grupo/línea, aplicando los
    efectos que estén prendidos. a0 = inicio del grupo (para calcular offsets en ms
    RELATIVOS al arranque de esa línea, que es como \\t los espera)."""
    partes = []
    for i, (palabra, wa, wb) in enumerate(grupo):
        limpio = palabra.replace("{", "(").replace("}", ")")
        base = PALETA_COLORES[i % len(PALETA_COLORES)] if colores else COLOR_BLANCO
        if karaoke:
            t0 = max(0, round((wa - a0) * 1000))
            resaltado = PALETA_COLORES[i % len(PALETA_COLORES)] if colores else COLOR_KARAOKE_DEFAULT
            # Blanco (o su color base) hasta que le toca, switch rápido (60ms) al
            # color de resaltado exactamente cuando arranca esa palabra. Se arma a
            # mano con \t en vez de \k nativo: \k depende de cómo cada reproductor
            # interprete Primary/Secondary y varía entre ellos — esto es 100% propio,
            # sin ambigüedad de qué color va antes y cuál después.
            partes.append(f"{{\\c{COLOR_BLANCO}\\t({t0},{t0+60},\\c{resaltado})}}{limpio}")
        elif colores:
            partes.append(f"{{\\c{base}}}{limpio}")
        else:
            partes.append(limpio)
    texto = " ".join(partes)
    if emojis and emoji_map:
        for palabra, _, _ in grupo:
            e = emoji_map.get(_normalizar_palabra(palabra))
            if e:
                texto += f" {e}"
                break   # uno solo por grupo: empapelar de emojis se lee peor, no mejor
    return texto


def _color_ass(hex_rgb: str) -> str | None:
    """"00EEFF" (RGB, como lo da cualquier selector de color) -> "&H00FFEE00" (ASS va
    en BGR). None si no es un hex válido: entonces queda el blanco de siempre."""
    h = (hex_rgb or "").strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        int(h, 16)
    except ValueError:
        return None
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _al_estilo_viral(palabras: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """Como el viral #1 (3,47 M): todo en minúscula y sin signos pegados. Una palabra
    que era solo un signo desaparece."""
    out = []
    for p, a, b in palabras:
        limpio = p.strip(SIGNOS).lower()
        if limpio:
            out.append((limpio, a, b))
    return out


def _encoger_si_no_entra(texto: str, font: str, font_size: int) -> str:
    """Si una línea suelta es más ancha que la pantalla, le baja el tamaño solo a
    ella (override \\fs). Con letra gigante de a 1 palabra, "aproximadamente" se
    saldría por los costados."""
    ancho = len(texto) * font_size * ANCHO_LETRA.get(font, ANCHO_LETRA_DEFAULT)
    if ancho <= ANCHO_UTIL:
        return ""
    return f"{{\\fs{int(font_size * ANCHO_UTIL / ancho)}}}"


def _prefijo_popin() -> str:
    """Rebote de escala para TODA la línea: arranca chica, pasa de largo (overshoot)
    y se asienta en 100% — los primeros 220ms de vida de cada grupo. \\t es relativo
    al Start de esa Dialogue, así que "cada frase" rebota apenas aparece, siempre."""
    return "{\\fscx55\\fscy55\\t(0,120,\\fscx112\\fscy112)\\t(120,220,\\fscx100\\fscy100)}"


def construir_ass(alignment: dict, out_path: Path, offset: float = 0.0,
                   font: str = FONT, font_size: int = FONT_SIZE,
                   outline: int = OUTLINE, margin_v: int = MARGIN_V,
                   karaoke: bool = False, popin: bool = False, colores: bool = False,
                   emojis: bool = False, emoji_map: str = "",
                   palabras_por_grupo: int = PALABRAS_POR_GRUPO, color: str = "",
                   minusculas: bool = False) -> Path | None:
    """Escribe un .ass con los subtítulos ya sincronizados. offset = segundos a correr
    todo (si la voz no arranca en 0). Devuelve None si no hay timing utilizable.

    font/font_size/outline/margin_v (30/08): antes eran fijos para todos los nichos —
    ahora cada producto puede tener los suyos (ver Niche.subtitle_*). Los defaults acá
    son los de siempre, así que un llamador que no los pase no cambia nada.

    karaoke/popin/colores/emojis (09/09): los 4 efectos "creativos", también por
    nicho — ver el bloque de arriba. Todos apagados = el look de siempre, byte a
    byte (ningún override ASS se agrega al texto).

    palabras_por_grupo/color/minusculas (02/11/2026): el estilo del viral #1 de
    hidroponía — 1 palabra por pantalla, celeste fijo, minúscula. Con los defaults
    no cambia nada."""
    palabras = palabras_de_alignment(alignment)
    if minusculas:
        palabras = _al_estilo_viral(palabras)
    if not palabras:
        log.warning("Sin alignment utilizable -> no genero subtítulos.")
        return None
    grupos = _agrupar(palabras, por_grupo=max(1, int(palabras_por_grupo or 1)))
    mapa = parsear_emoji_map(emoji_map) if emojis else {}
    primario = _color_ass(color) or "&H00FFFFFF"

    cabecera = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {PLAY_W}\nPlayResY: {PLAY_H}\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Colores ASS = &HAABBGGRR. Texto blanco, borde y sombra negros.
        f"Style: Def,{font},{font_size},{primario},&H000000FF,&H00000000,&H96000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},4,2,60,60,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lineas = []
    for i, grupo in enumerate(grupos):
        a = grupo[0][1] + offset
        b = max(grupo[-1][2] + offset, a + 0.35)   # mínimo legible
        # Nunca encima de la siguiente: si se pisan, libass apila las dos líneas
        # (visto 02/11/2026 en la nube: "completamente" arriba de "es").
        if i + 1 < len(grupos):
            b = min(b, grupos[i + 1][0][1] + offset)
        cuerpo = _texto_grupo(grupo, grupo[0][1], karaoke, colores, emojis, mapa)
        cuerpo = _encoger_si_no_entra(" ".join(p[0] for p in grupo), font, font_size) + cuerpo
        if popin:
            cuerpo = _prefijo_popin() + cuerpo
        lineas.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Def,,0,0,0,,{cuerpo}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(cabecera + "\n".join(lineas) + "\n", encoding="utf-8")
    log.info("Subtítulos generados -> %s (%d bloques)", out_path.name, len(grupos))
    return out_path
