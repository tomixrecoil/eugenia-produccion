"""
Carga de configuración: variables de entorno (.env) + config del nicho (YAML).
"""
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# SIN VENTANAS NEGRAS EN WINDOWS
# ---------------------------------------------------------------------------
# El sistema llama a ffmpeg, wrangler y yt-dlp por subprocess. En Windows cada
# llamada abre (y cierra) una consola: molesta y da sensación de que "algo raro
# pasa". Se parchea Popen una sola vez acá —config lo importa TODO el proyecto—
# en vez de tocar las 24 llamadas repartidas. La salida se sigue capturando igual.
if sys.platform == "win32" and not getattr(subprocess, "_sin_ventana_aplicado", False):
    _CREATE_NO_WINDOW = 0x08000000
    _PopenOriginal = subprocess.Popen

    class _PopenSilencioso(_PopenOriginal):  # type: ignore[misc,valid-type]
        def __init__(self, *args, **kwargs):
            if not kwargs.get("shell"):
                kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
            else:
                # Con shell=True el flag no alcanza: se oculta la ventana del cmd.
                si = kwargs.get("startupinfo") or subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0  # SW_HIDE
                kwargs["startupinfo"] = si
            super().__init__(*args, **kwargs)

    subprocess.Popen = _PopenSilencioso  # type: ignore[misc]
    subprocess._sin_ventana_aplicado = True  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Mapa por defecto de subtítulos con emoji (09/09) -- editable por nicho desde el
# panel (Subtítulos), una línea "palabra=emoji" por par. Genérico a propósito: sirve
# de punto de partida para cualquier nicho, no solo el de hoy.
SUBTITLE_EMOJI_MAP_DEFAULT = """agua=💧
riego=💧
dinero=💰
gratis=🎁
facil=👌
fácil=👌
rapido=⚡
rápido=⚡
crece=🌱
crecer=🌱
planta=🌱
plantas=🌱
cultivo=🌱
cosecha=🌾
sol=☀️
casa=🏠
tiempo=⏰
gracias=🙏
increible=🤯
increíble=🤯
secreto=🤫
importante=❗"""


@dataclass
class Niche:
    name: str
    # (02/11/2026: fuera `producir_activo`, la pausa manual del nicho. Repetía al
    # interruptor ⚙️ Producción de state/toggles.json, que es el que mira la nube.)
    tiktok_profile: str
    scan_count: int
    top_k: int
    min_views: int
    meta_page_id: str
    meta_business_id: str
    publish_state: str
    publish_facebook: bool
    publish_instagram: bool
    publish_youtube: bool
    publish_tiktok: bool      # a futuro: la API de TikTok necesita auditoría aprobada
    # Fuentes EXTRA de contenido (opcionales): hasta 4 perfiles de TikTok y 3 canales
    # de YouTube. Ver SLOTS_FUENTE y fuentes_detalle().
    tiktok_profile_2: str
    tiktok_profile_3: str
    tiktok_profile_4: str
    youtube_source_1: str
    youtube_source_2: str
    youtube_source_3: str
    # Carpeta local con videos propios (ej: la carpeta catalogada de @Bonsais). Libre:
    # cualquier carpeta con archivos de video, sin exigirle la estructura ni el sello
    # "revisado2" que sí exige la fábrica de stock (producir_stock.py).
    carpeta_local: str
    # Con esto prendido, Ejecutar ignora TikTok/YouTube (aunque tengan URL cargada) y la
    # ÚNICA fuente es carpeta_local. Apagado = se suma a los slots de siempre.
    solo_carpeta_local: bool
    # Nombres de slot apagados sin borrarles la URL, ej: [tiktok_profile_3]
    fuentes_apagadas: list
    cta_link: str
    # El switch landing/checkout de la pestaña Nicho. `cta_link` es el que YA quedó
    # resuelto (lo calcula la interfaz al guardar) y es el que usa todo el sistema; estos
    # tres se guardan además para poder alternar sin volver a pegar las URLs. Hacían falta
    # acá arriba porque `sync_precios.py` necesita el CHECKOUT aunque el nicho esté
    # apuntando a la landing: los precios por país solo se pueden scrapear de Hotmart.
    cta_modo: str        # "landing" | "checkout"
    cta_landing: str
    cta_checkout: str
    copy_engine: str
    # --- identidad del producto ---
    # Con un solo nicho estos textos vivían en el código o en variables de entorno
    # GLOBALES (NICHE_LABEL, YT_TAGS, YT_HASHTAGS, PRODUCTO_NOMBRE), que son de proceso:
    # no pueden valer tres cosas a la vez. Vacío = se comporta igual que siempre.
    tema: str                # cómo se nombra el tema: "hidroponía", "bonsái"
    producto_nombre: str     # "Curso Completo de Hidroponía"
    # Cómo se llama el NEGOCIO, que no es lo mismo que el producto: Eugenia se presenta
    # como "de Bonsái en Casa", no como "de Bonsai en casa desde cero". Vacío = se usa el nombre
    # del producto, que es como se comportaba antes de que existiera este campo.
    negocio: str             # "Bonsái en Casa", "Ecosistema Hidropónico"
    # El % de descuento que se promete. Estaba clavado en el prompt del Worker, con un
    # 60 que se le decía a TODOS: los leads de hidroponía escuchaban 60 cuando la oferta
    # real era 80. Vacío o 0 = Eugenia no menciona ningún descuento, que es más seguro
    # que inventar uno.
    descuento: int           # 60, 80…
    yt_tags: list            # etiquetas del Short; vacío = las de siempre
    yt_hashtags: str         # línea de hashtags de la descripción; vacío = la de siempre
    # --- audio / doblaje ---
    audio_mode: str          # "auto" (detectar y procesar) | "keep" (no tocar audio)
    voiceover_when_silent: bool
    english_policy: str      # "dub" (mutear + doblar es) | "discard" (saltar el video)
    elevenlabs_voice: str    # nombre o voice_id
    elevenlabs_model: str
    voice_speed: float       # 1.0 = normal · 2.0 = el doble de rápido
    # --- mockup ---
    add_mockup: bool
    # Logo de la marca: marca de agua durante TODO el video.
    add_logo: bool
    logo_file: str
    logo_scale: float
    logo_position: str
    mockup_file: str
    mockup_seconds: int
    mockup_scale: float
    mockup_position: str     # bottom | center | top
    # --- subtítulos --- (30/08: antes eran constantes fijas en src/subtitles.py,
    # iguales para todos los nichos; ahora por producto, como logo/mockup)
    subtitle_font: str
    subtitle_font_size: int
    subtitle_outline: int
    subtitle_margin_v: int   # distancia desde abajo del video
    # --- subtítulos "creativos" (09/09, a pedido de Tomix) --- cada uno es un
    # interruptor independiente: se pueden combinar todos, ninguno, o algunos.
    subtitle_karaoke: bool       # cada palabra cambia de color blanco->resaltado al decirse
    subtitle_popin: bool         # cada grupo entra con rebote de escala (chico->grande->normal)
    subtitle_colores: bool       # paleta rotativa por palabra en vez de blanco monocromo
    subtitle_emojis: bool        # inserta un emoji si alguna palabra del grupo matchea el mapa
    subtitle_emoji_map: str      # editable: una línea por par "palabra=emoji"
    # --- estilo del viral #1 (02/11/2026): 1 palabra, color fijo, minúscula ---
    subtitle_palabras: int       # palabras por pantalla (el viral: 1)
    subtitle_color: str          # color fijo en hex RGB ("00EEFF"); vacío = blanco
    subtitle_minusculas: bool    # todo en minúscula y sin signos, como el viral
    # --- programación ---
    schedule_enabled: bool
    schedule_times: list     # ["05:00", "18:00"]
    gemini_prompt: str
    gpt_prompt: str


@dataclass
class Secrets:
    gemini_api_key: str
    gemini_model: str
    openai_api_key: str
    openai_model: str
    meta_page_token: str
    meta_graph_version: str
    meta_app_id: str
    meta_app_secret: str
    elevenlabs_api_key: str
    r2_bucket: str
    r2_public_base: str
    whatsapp_token: str
    whatsapp_phone_id: str
    whatsapp_waba_id: str


def _read_prompt(rel_path: str) -> str:
    p = ROOT / rel_path
    if not p.exists():
        raise FileNotFoundError(f"No se encontró el prompt: {p}")
    return p.read_text(encoding="utf-8").strip()


def load_niche(name: str) -> Niche:
    path = ROOT / "niches" / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No existe el nicho '{name}'. Buscado en: {path}\n"
            f"Nichos disponibles: {[p.stem for p in (ROOT / 'niches').glob('*.yaml')]}"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Niche(
        name=data["name"],
        tiktok_profile=data["tiktok_profile"],
        scan_count=int(data.get("scan_count", 30)),
        top_k=int(data.get("top_k", 3)),
        min_views=int(data.get("min_views", 0)),
        meta_page_id=str(data["meta_page_id"]),
        meta_business_id=str(data.get("meta_business_id", "")),
        publish_state=data.get("publish_state", "PUBLISHED"),
        publish_facebook=bool(data.get("publish_facebook", True)),
        publish_instagram=bool(data.get("publish_instagram", True)),
        publish_youtube=bool(data.get("publish_youtube", True)),
        publish_tiktok=bool(data.get("publish_tiktok", False)),
        tiktok_profile_2=data.get("tiktok_profile_2", "") or "",
        tiktok_profile_3=data.get("tiktok_profile_3", "") or "",
        tiktok_profile_4=data.get("tiktok_profile_4", "") or "",
        youtube_source_1=data.get("youtube_source_1", "") or "",
        youtube_source_2=data.get("youtube_source_2", "") or "",
        youtube_source_3=data.get("youtube_source_3", "") or "",
        carpeta_local=data.get("carpeta_local", "") or "",
        solo_carpeta_local=bool(data.get("solo_carpeta_local", False)),
        fuentes_apagadas=list(data.get("fuentes_apagadas") or []),
        cta_link=data.get("cta_link", ""),
        # Migración de los nichos viejos, que solo tenían cta_link: si la URL es de
        # Hotmart se la reconoce como checkout, si no como landing. Igual criterio que
        # usa la interfaz, para que las dos vean lo mismo.
        cta_modo=data.get("cta_modo") or (
            "checkout" if "hotmart" in (data.get("cta_link") or "").lower() else "landing"),
        cta_landing=data.get("cta_landing") or (
            "" if "hotmart" in (data.get("cta_link") or "").lower() else (data.get("cta_link") or "")),
        cta_checkout=data.get("cta_checkout") or (
            (data.get("cta_link") or "") if "hotmart" in (data.get("cta_link") or "").lower() else ""),
        copy_engine=data.get("copy_engine", "openai"),
        tema=data.get("tema", "") or "",
        producto_nombre=data.get("producto_nombre", "") or "",
        negocio=data.get("negocio", "") or "",
        descuento=int(data.get("descuento") or 0),
        yt_tags=list(data.get("yt_tags") or []),
        yt_hashtags=data.get("yt_hashtags", "") or "",
        audio_mode=data.get("audio_mode", "auto"),
        voiceover_when_silent=bool(data.get("voiceover_when_silent", True)),
        english_policy=data.get("english_policy", "dub"),
        elevenlabs_voice=data.get("elevenlabs_voice", VOZ_ELEVENLABS_DEFAULT),
        elevenlabs_model=data.get("elevenlabs_model", "eleven_multilingual_v2"),
        voice_speed=float(data.get("voice_speed", VELOCIDAD_VOZ_DEFAULT) or VELOCIDAD_VOZ_DEFAULT),
        add_mockup=bool(data.get("add_mockup", False)),
        add_logo=bool(data.get("add_logo", False)),
        logo_file=data.get("logo_file", "") or "",
        logo_scale=float(data.get("logo_scale", 0.35) or 0.35),
        logo_position=data.get("logo_position", "top") or "top",
        mockup_file=data.get("mockup_file", "assets/mockup.png"),
        mockup_seconds=int(data.get("mockup_seconds", 12)),
        mockup_scale=float(data.get("mockup_scale", 0.5)),
        mockup_position=data.get("mockup_position", "bottom"),
        subtitle_font=data.get("subtitle_font", "Arial Black") or "Arial Black",
        subtitle_font_size=int(data.get("subtitle_font_size", 92) or 92),
        subtitle_karaoke=bool(data.get("subtitle_karaoke", False)),
        subtitle_popin=bool(data.get("subtitle_popin", False)),
        subtitle_colores=bool(data.get("subtitle_colores", False)),
        subtitle_emojis=bool(data.get("subtitle_emojis", False)),
        subtitle_emoji_map=data.get("subtitle_emoji_map", "") or SUBTITLE_EMOJI_MAP_DEFAULT,
        subtitle_outline=int(data.get("subtitle_outline", 7) or 7),
        subtitle_margin_v=int(data.get("subtitle_margin_v", 520) or 520),
        subtitle_palabras=int(data.get("subtitle_palabras", 3) or 3),
        subtitle_color=str(data.get("subtitle_color", "") or "").strip().lstrip("#"),
        subtitle_minusculas=bool(data.get("subtitle_minusculas", False)),
        schedule_enabled=bool(data.get("schedule_enabled", False)),
        schedule_times=(data.get("schedule_times")
                        or ([data["schedule_time"]] if data.get("schedule_time") else ["18:00"])),
        gemini_prompt=_read_prompt(data["gemini_prompt_file"]),
        gpt_prompt=_read_prompt(data["gpt_prompt_file"]),
    )


def load_secrets() -> Secrets:
    # Releer .env en cada llamada para reflejar cambios hechos desde la web.
    load_dotenv(ROOT / ".env", override=True)
    return Secrets(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        meta_page_token=os.getenv("META_PAGE_ACCESS_TOKEN", ""),
        meta_graph_version=os.getenv("META_GRAPH_VERSION", "v21.0"),
        meta_app_id=os.getenv("META_APP_ID", ""),
        meta_app_secret=os.getenv("META_APP_SECRET", ""),
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
        r2_bucket=os.getenv("R2_BUCKET", ""),
        r2_public_base=os.getenv("R2_PUBLIC_BASE", ""),
        whatsapp_token=os.getenv("WHATSAPP_TOKEN", ""),
        whatsapp_phone_id=os.getenv("WHATSAPP_PHONE_ID", ""),
        whatsapp_waba_id=os.getenv("WHATSAPP_WABA_ID", ""),
    )


# Tokens de página ya derivados, por id de página. Publicar un reel toca la API de Meta
# varias veces y derivar cuesta una llamada: sin esta memoria serían 4 o 5 de más por reel.
_PAGE_TOKENS: dict[str, str] = {}


def token_de_pagina(page_id: str, s: "Secrets | None" = None) -> str:
    """Devuelve el token de LA página que se le pida.

    Por qué existe
    --------------
    Un Page Token sirve para UNA sola página. Con un nicho alcanzaba con guardar uno en
    el .env; con tres no: /api/meta/connect guarda el token en la clave GLOBAL
    META_PAGE_ACCESS_TOKEN, así que conectar la página de bonsái PISABA la de hidroponía
    y hidroponía dejaba de publicar en Facebook y en Instagram sin aviso (el chip de la
    interfaz seguía diciendo "conectado").

    El token de SISTEMA (WHATSAPP_TOKEN) no tiene ese problema: es de un usuario de
    sistema del negocio, llega a las 4 páginas con permiso de crear contenido, y de él se
    deriva el de cada página en el momento. Uno guardado, todos disponibles.

    Y arregla una bomba aparte: el page token que hay guardado nació de un login humano,
    así que su ACCESO A DATOS vence a los 90 días (el actual, el 02/10/2026). Cuando eso
    pasa el token sigue pareciendo válido pero las respuestas vuelven vacías, o sea que
    falla como si todo estuviera roto sin motivo. El derivado del token de sistema tiene
    los dos relojes en cero: no vence nunca.

    Si no hay token de sistema, o si Meta no contesta, cae al META_PAGE_ACCESS_TOKEN de
    siempre: nunca deja a nadie sin poder publicar por culpa de este cambio.
    """
    s = s or load_secrets()
    page_id = str(page_id or "").strip()
    if not page_id:
        return s.meta_page_token
    if page_id in _PAGE_TOKENS:
        return _PAGE_TOKENS[page_id]
    if not s.whatsapp_token:
        return s.meta_page_token
    try:
        import requests
        r = requests.get(
            f"https://graph.facebook.com/{s.meta_graph_version}/me/accounts",
            params={"access_token": s.whatsapp_token, "fields": "id,access_token", "limit": 100},
            timeout=30).json()
        for p in r.get("data") or []:
            if p.get("access_token"):
                _PAGE_TOKENS[str(p["id"])] = p["access_token"]
        if page_id in _PAGE_TOKENS:
            return _PAGE_TOKENS[page_id]
        logging.getLogger("marketing_agent").warning(
            "El token de sistema no llega a la página %s (¿está en otro negocio?) — "
            "uso el META_PAGE_ACCESS_TOKEN guardado.", page_id)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("marketing_agent").warning(
            "No pude derivar el token de la página %s (%s) — uso el guardado.",
            page_id, str(e)[:80])
    return s.meta_page_token


def validate_secrets(s: Secrets, need_publish: bool = True,
                     copy_engine: str = "openai", need_voice: bool = False) -> list[str]:
    """Devuelve lista de credenciales faltantes (vacía = todo OK)."""
    missing = []
    if not s.gemini_api_key:
        missing.append("GEMINI_API_KEY")
    if copy_engine == "openai" and not s.openai_api_key:
        missing.append("OPENAI_API_KEY")
    # Alcanza con CUALQUIERA de los dos: del token de sistema se deriva el de cada
    # página (ver token_de_pagina), así que tenerlo es tan bueno como tener el de página.
    if need_publish and not (s.meta_page_token or s.whatsapp_token):
        missing.append("META_PAGE_ACCESS_TOKEN")
    if need_voice and not s.elevenlabs_api_key:
        missing.append("ELEVENLABS_API_KEY")
    return missing


def niche_needs_voice(n: "Niche") -> bool:
    """True si el nicho puede necesitar TTS (doblaje o voz para videos mudos)."""
    return n.audio_mode == "auto" and (n.english_policy == "dub" or n.voiceover_when_silent)


def prompt_de(archivo: str, por_defecto: str) -> str:
    """Lee un prompt de prompts/<archivo>. Si no existe (o está vacío) devuelve el valor
    por defecto que trae el código: así el sistema nunca se rompe por un archivo faltante
    y a la vez todos los prompts se pueden editar desde la app."""
    p = ROOT / "prompts" / archivo
    try:
        if p.exists():
            txt = p.read_text(encoding="utf-8").strip()
            if txt:
                return txt
    except Exception:
        pass
    return por_defecto


def prompt_de_nicho(nicho: str, archivo: str, por_defecto: str) -> str:
    """El prompt del nicho si lo tiene, si no el compartido, si no el del código.

    Los prompts de VOZ (voz_describe, voz_traducir, voz_comun, voz_tono)
    y las estructuras de copy se leían sin ninguna noción de nicho, y su contenido es de
    hidroponía: hablan de germinación, de la bomba y del riego automatizado, y obligan a
    cerrar con "Comenta CULTIVO". Un reel de bonsái habría recibido un guion sobre
    bombas de riego.

    La convención es prompts/<nicho>_<archivo>. Mientras un nicho no tenga el suyo, usa
    el compartido exactamente como hasta ahora: hidroponía no cambia en nada.
    """
    n = (nicho or "").strip()
    if n:
        propio = prompt_de(f"{n}_{archivo}", "")
        if propio:
            return propio
    return prompt_de(archivo, por_defecto)


def sck(*partes) -> str:
    """Arma el código de origen que se le cuelga al checkout (parámetro `sck`).

    POR QUÉ EXISTE
    --------------
    Hotmart NO devuelve de dónde vino una venta salvo que el link lo diga. Sin esto,
    saber el origen de UNA venta es una investigación forense de horas cruzando horas,
    nombres y mails contra cada canal — y para la mitad de las ventas termina en "no se
    puede determinar". Con esto, Hotmart lo devuelve solo en `purchase.tracking.source_sck`.

    Las reglas son de Hotmart y romperlas no da error: simplemente descarta el código y
    la venta vuelve a quedar sin origen.
      - máximo 30 caracteres
      - el guión bajo `_` está PROHIBIDO (Hotmart lo reserva para uso interno)
      - sin espacios ni acentos

    SEPARADOR: se usa el guión `-`, NO la barra `|` que sugiere Hotmart. La barra no es
    un carácter válido en una URL (RFC 3986) y WhatsApp, Instagram y YouTube detectan
    los links automáticamente CORTANDO donde aparece un carácter inválido: el link se
    partía en "...&sck=wa" y "|euge" quedaba como texto suelto al lado. El guión es
    válido en URLs, no lo toca ningún cliente, y Hotmart lo acepta igual (probado: el
    checkout devuelve exactamente el mismo HTML, con los 3 order bumps intactos).

    Se usa `sck` y no `src` a propósito: `src` es para links de afiliado y páginas de
    venta intermedias; `sck` es el que Hotmart define para campañas que mandan tráfico
    DIRECTO al checkout, que es exactamente lo que hace todo este sistema.

    Ejemplos:
        sck("wa", "segui")        -> "wa-segui"
        sck("ig", "r", video_id)  -> "ig-r-8293931101"   (el id se recorta solo)
    """
    import re as _re
    import unicodedata as _ud
    limpias = []
    for p in partes:
        t = str(p or "").strip().lower()
        if not t:
            continue
        # sin acentos: Hotmart no los documenta como válidos y no vale el riesgo
        t = "".join(c for c in _ud.normalize("NFKD", t) if not _ud.combining(c))
        # el guión bajo está prohibido -> se convierte, no se borra (si no, "reel_3" y
        # "reel3" colapsarían en el mismo código y se mezclarían dos orígenes distintos)
        t = t.replace("_", "-")
        t = _re.sub(r"[^a-z0-9.-]+", "-", t).strip("-")
        if t:
            limpias.append(t)
    if not limpias:
        return ""
    codigo = "-".join(limpias)
    if len(codigo) <= 30:
        return codigo
    # Se recorta la ÚLTIMA parte (que es el id del contenido) y se conserva la cola, que
    # es la que distingue un reel de otro. Recortar por el principio borraría el canal.
    cabeza = "-".join(limpias[:-1])
    espacio = 30 - len(cabeza) - (1 if cabeza else 0)
    cola = limpias[-1][-espacio:] if espacio > 0 else ""
    return ("-".join([cabeza, cola]) if cabeza and cola else (cabeza or cola))[:30]


def checkout(niche_name: str | None = None, origen: str | None = None) -> str:
    """El link de venta del nicho activo. FUENTE ÚNICA: todo el sistema (videos, mails,
    comentarios, YouTube, Eugenia) lo saca de acá, así se cambia en un solo lugar
    —la pestaña Nicho— y no hay que tocar código.

    `origen` es el código de `sck()`. Si se pasa, el link sale etiquetado y Hotmart
    devuelve ese código en la venta. Sin `origen` el link sale como siempre, así que
    ningún llamador viejo se rompe.
    """
    try:
        base = load_niche(niche_name or os.getenv("NICHE", "hidroponia")).cta_link or ""
    except Exception:
        return ""
    if not base or not origen:
        return base
    # El `sck` es un parámetro de HOTMART. Pegado a una landing propia no etiqueta nada:
    # ensucia la URL a la vista del cliente y la venta sigue sin poder atribuirse. Desde
    # que el nicho puede apuntar a una landing (switch landing/checkout), etiquetar a
    # ciegas dejaba enlaces como "conocimientosdigital.com/bonsai/?sck=ig-r".
    if "hotmart.com" not in base.lower():
        return base
    codigo = sck(origen)
    if not codigo:
        return base
    # Si el link ya traía un sck (por ejemplo, cargado a mano en la pestaña Nicho), se
    # respeta el que ya estaba: es una decisión explícita del dueño.
    if "sck=" in base:
        return base
    return base + ("&" if "?" in base else "?") + "sck=" + codigo


# Los slots de fuente, en orden y con el nombre que ve la persona. Es el ÚNICO lugar
# donde se declara la lista: de acá salen fuentes_de(), la interfaz y el "un video por
# slot encendido" del dry run. Para sumar un slot nuevo se agrega acá, en la dataclass
# Niche y en NICHE_FIELDS_DEFAULT.
SLOTS_FUENTE = [
    ("tiktok_profile",   "TikTok principal"),
    ("tiktok_profile_2", "TikTok 2"),
    ("tiktok_profile_3", "TikTok 3"),
    ("tiktok_profile_4", "TikTok 4"),
    ("youtube_source_1", "YouTube 1"),
    ("youtube_source_2", "YouTube 2"),
    ("youtube_source_3", "YouTube 3"),
]


def fuentes_detalle(n: "Niche") -> list[dict]:
    """Los slots con su estado, para la interfaz y para el dry run por slot.

    Un slot está ENCENDIDO si tiene una URL y no figura en `fuentes_apagadas`. El
    apagado se guarda como lista de nombres de slot en vez de un booleano por slot para
    que agregar un slot no obligue a agregar también su interruptor en los tres lugares
    del YAML — y para que el archivo se lea solo:

        fuentes_apagadas: [tiktok_profile_3, youtube_source_1]

    Un slot apagado CONSERVA su URL: apagarlo no es borrarlo.

    Con `solo_carpeta_local` prendido, TODOS estos slots salen `activo=False` aunque
    tengan URL y no estén en `fuentes_apagadas`: la interfaz tiene que mostrarlos
    apagados, no solo ignorarlos puertas adentro.
    """
    apagadas = set(getattr(n, "fuentes_apagadas", None) or [])
    solo_local = bool(getattr(n, "solo_carpeta_local", False))
    vistas: set[str] = set()
    out = []
    for campo, etiqueta in SLOTS_FUENTE:
        url = (getattr(n, campo, "") or "").strip()
        # El mismo perfil en dos slots se escanearía dos veces y competiría consigo mismo.
        repetida = bool(url) and url in vistas
        if url:
            vistas.add(url)
        out.append({
            "slot": campo, "etiqueta": etiqueta, "url": url,
            "activo": bool(url) and campo not in apagadas and not repetida and not solo_local,
            "repetida": repetida,
        })
    return out


def fuentes_de(n: "Niche") -> list[str]:
    """Los perfiles ENCENDIDOS de donde sacar contenido, sin vacíos ni repetidos.
    Devuelve al menos el perfil principal, así nada cambia si se apagó todo por error."""
    out = [f["url"] for f in fuentes_detalle(n) if f["activo"]]
    return out or [n.tiktok_profile]


def nicho_produce(name: str) -> tuple[bool, str]:
    """¿Este nicho está listo para producir? (sí/no, motivo si no).

    Listo = tiene de dónde sacar contenido Y a dónde mandar al que compra. Un nicho a
    medio configurar (numerología: sin fuentes y con el link en "PENDIENTE") no está
    roto, está incompleto: produciría un video sin fuente o mandaría la palabra
    PENDIENTE como link de venta.
    """
    try:
        n = load_niche(name)
    except Exception as e:  # noqa: BLE001
        return False, f"no se puede leer su configuración ({str(e)[:60]})"
    if not [u for u in fuentes_de(n) if (u or "").strip()]:
        return False, "sin ninguna fuente de contenido cargada"
    if not str(n.cta_link or "").lower().startswith("http"):
        return False, f"el link de venta no es una URL ({n.cta_link!r})"
    # "PENDIENTE" es el placeholder que deja la interfaz cuando todavía no se cargó
    # el nombre real del producto (09/09: numerología tenía fuente y link reales
    # pero el nombre sin completar, y igual entraba a producir — publicaría con
    # "PENDIENTE" en el copy de venta).
    if not str(n.producto_nombre or "").strip() or n.producto_nombre.strip().upper() == "PENDIENTE":
        return False, "el nombre del producto sigue en PENDIENTE"
    return True, ""


def nichos_produccion() -> list[str]:
    """Los nichos que HOY pueden producir, en orden alfabético.

    FUENTE ÚNICA de la lista de nichos activos. Antes cada script traía la suya escrita
    a mano (`NICHOS = ["hidroponia", "bonsai"]` en productor_diario, dicts en
    producir_stock, colas en encolar_stock, el enum de ordenes_ia): un nicho nuevo
    quedaba invisible para todos ellos aunque estuviera bien configurado, y había que
    acordarse de los cuatro lugares. Los que no están listos se saltean con motivo
    (ver nicho_produce), no se rompen ni frenan a los demás.
    """
    return [n for n in list_niches() if nicho_produce(n)[0]]


# ==========================================================================
# Helpers para la interfaz web (leer/escribir .env y nichos)
# ==========================================================================

ENV_PATH = ROOT / ".env"
NICHES_DIR = ROOT / "niches"

ENV_KEYS = [
    # La clave del panel. Vivia SOLO en PANEL_KEY.txt y no estaba en esta lista, asi que
    # config.read_env() la devolvia vacia: cualquier script que llamara a un endpoint
    # protegido del Worker iba con clave vacia y recibia 401 sin entender por que.
    "PANEL_KEY",
    # Cobro por transferencia en Argentina, por fuera de Hotmart. Es lo que Eugenia le
    # ofrece a un lead argentino que quiere comprar. Si falta cualquiera de los dos, NO
    # se ofrece: mandar un alias a medias es peor que no mencionarlo.
    "ALIAS_AR", "MONTO_AR", "CBU_AR", "BANCO_AR",
    "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_MODEL",
    "OPENAI_API_KEY", "OPENAI_MODEL",
    # Groq (29/08): vivia SOLO como secreto de Cloudflare, invisible para read_env() y
    # para guardar_credenciales.py. 3 cuentas para sumar cupo (el gratis se agota rapido
    # con varias charlas de leads en simultaneo, ver /wa-groq?listar=1).
    "GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3",
    "META_PAGE_ACCESS_TOKEN", "META_GRAPH_VERSION",
    "META_APP_ID", "META_APP_SECRET",
    "ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY_2", "ELEVENLABS_API_KEY_3",
    "R2_BUCKET", "R2_PUBLIC_BASE",
    "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_WABA_ID",
    # Hotmart: para verificar compras antes de reenviar accesos.
    # Se sacan en Hotmart -> Herramientas -> Credenciales API (developers.hotmart.com)
    "HOTMART_CLIENT_ID", "HOTMART_CLIENT_SECRET", "HOTMART_BASIC",
    # El hottok de la cuenta PRINCIPAL (hidroponía/bonsái) — vivía SOLO como secreto de
    # Cloudflare (WORKER_SECRET_KEYS ya lo tenía), invisible para read_env()/keyring hasta
    # el 29/08, mismo problema que paso con GROQ_API_KEY.
    "HOTMART_HOTTOK",
    # Segunda cuenta de Hotmart (numerología / Sersoular, es de otra persona). El hottok
    # es SOLO para validar que un webhook entrante viene de verdad de Hotmart; no sirve
    # para consultar ventas: eso necesita su propio CLIENT_ID/SECRET/BASIC.
    "HOTMART_HOTTOK_NUMEROLOGIA",
    # Métricas de publicidad y campañas de email (se editan desde la pestaña Credenciales).
    "AD_ACCOUNT_ID", "GMAIL_ECOSISTEMA_USER", "GMAIL_ECOSISTEMA_PASS",
    # ID de la página de Facebook. Los scripts lo leen de acá (antes estaba pegado en
    # el código); así otro usuario pone la suya sin tocar nada.
    "META_PAGE_ID",
    # Claude (Anthropic): para asistencia con Claude Code sobre este proyecto.
    "ANTHROPIC_API_KEY",
    # Token de sistema de la app de Meta "Kontrol" (29/08). Permisos amplios (WhatsApp,
    # Instagram, Ads, paginas) — candidato fuerte a reemplazar WHATSAPP_TOKEN si ese se
    # cae, pero NO se pisa el que ya esta en produccion sin que Tomix lo confirme: lo usan
    # todas las conversaciones activas. Guardado aparte hasta que diga para que va.
    "META_TOKEN_KONTROL",
    # --- Claves que el sistema YA usaba pero no figuraban acá -------------------
    # No estar en la lista significaba ser invisible para read_env(): la interfaz
    # no las mostraba y no había forma de editarlas sin abrir el .env a mano.
    # La 4ta key de rotación: src/gemini_client.py y src/voiceover.py ya la leen.
    "GEMINI_API_KEY_4", "ELEVENLABS_API_KEY_4",
    # 5ta cuenta (elevacion.desarrollo.personal, 18/08/2026). Ver CUENTAS_API.md.
    "GEMINI_API_KEY_5", "ELEVENLABS_API_KEY_5",
    # 6ta cuenta (, 04/09/2026). Ver VAULT_CREDENCIALES.md.
    "GEMINI_API_KEY_6",
    # Voz clonada de Sylvana para las notas de voz (webapp.py).
    "ELEVEN_SYLVANA_KEY",
    # Zona horaria del negocio para cortar "hoy"/"semana" en el embudo (webapp.py).
    "EMBUDO_TZ",
    # 2da casilla de Gmail: leer_emails.py la usa para la cuenta "payoneer".
    "GMAIL_PAYONEER_USER", "GMAIL_PAYONEER_PASS",
    # A dónde avisar cuando entra una venta / hay un problema (monitor_ventas.py, src/notify.py).
    "ALERT_EMAIL",
    # Respaldo del mail: si Gmail rechaza (contrasena de aplicacion vencida),
    # la alerta se manda a este WhatsApp. Numero con codigo de pais, sin +.
    "ALERT_WHATSAPP",
    # Carpeta madre de Drive donde viven los cursos (drive_cursos.py).
    "DRIVE_MADRE_ID",
    # Ads: cuenta alternativa y token propio con ads_read (webapp.py, panel de gasto).
    "META_AD_ACCOUNT_ID", "META_ADS_TOKEN",
    # Llaves de la bóveda de credenciales en la nube (boveda.py, analisis/REDISENO_0211.md).
    "BOVEDA_KEY", "BOVEDA_PRODUCCION_KEY",
    # Clave de la puerta de GitHub a R2 (también abre /whisper). SIN la URL a propósito: con
    # PUERTA_R2_URL en el entorno, r2io cree que está en la nube.
    "PUERTA_R2_KEY",
    # OJO: NICHE (config.py, postear_ganadores.py, subir_youtube.py, sync_precios.py)
    # queda A PROPÓSITO fuera de la lista: se lee con os.getenv("NICHE", "hidroponia")
    # y un valor VACÍO no activa ese default -> load_niche("") explota y el checkout
    # se queda sin link. El nicho activo se elige en la app, no en el .env.
]

# Voz por defecto de TODAS las cuentas de ElevenLabs: profesional latina.
# ("Antoni" ErXwo... es solo el respaldo gratis cuando la cuenta no tiene saldo.)
VOZ_ELEVENLABS_DEFAULT = "htFfPSZGJwjBv1CL0aMD"   # Antonio – Confident Conversational Latino

# A velocidad 1.0 esta voz habla demasiado lento para un reel. 1.25 es el ritmo
# elegido después de probar 2.0 (muy rápido) y 1.4 (todavía rápido).
VELOCIDAD_VOZ_DEFAULT = 1.25

NICHE_FIELDS_DEFAULT = {
    "name": "",
    "tiktok_profile": "",
    "scan_count": 30,
    "top_k": 3,
    "min_views": 50000,
    "meta_page_id": "",
    "meta_business_id": "",
    "publish_state": "PUBLISHED",
    "publish_facebook": True,
    "publish_instagram": True,
    "publish_youtube": True,
    "publish_tiktok": False,
    "tiktok_profile_2": "",
    "tiktok_profile_3": "",
    "tiktok_profile_4": "",
    "youtube_source_1": "",
    "youtube_source_2": "",
    "youtube_source_3": "",
    "carpeta_local": "",
    "solo_carpeta_local": False,
    "fuentes_apagadas": [],
    "cta_link": "",
    # Switch de link de venta (Ajustes → Mi producto): se guardan LOS DOS destinos y
    # cta_modo dice cuál está saliendo. cta_link sigue siendo el único campo que el
    # resto del código consume — el switch solo decide qué valor lleva.
    "cta_modo": "",
    "cta_landing": "",
    "cta_checkout": "",
    # Gemini por defecto: es gratis y ya está configurado. Con "openai" un nicho nuevo
    # nacía atado a un motor pago, y si esa cuenta se queda sin crédito el reel se pierde
    # con el video ya renderizado. Pasó al crear bonsái.
    "copy_engine": "gemini",
    "tema": "",
    "producto_nombre": "",
    "negocio": "",
    "descuento": 0,
    "yt_tags": [],
    "yt_hashtags": "",
    "audio_mode": "auto",
    "voiceover_when_silent": True,
    "english_policy": "dub",
    "elevenlabs_voice": VOZ_ELEVENLABS_DEFAULT,
    "elevenlabs_model": "eleven_multilingual_v2",
    "voice_speed": VELOCIDAD_VOZ_DEFAULT,
    "add_mockup": False,
    "add_logo": False,
    "logo_file": "",
    "logo_scale": 0.35,
    "logo_position": "top",
    "mockup_file": "assets/mockup.png",
    "mockup_seconds": 12,
    "mockup_scale": 0.5,
    "mockup_position": "bottom",
    "subtitle_font": "Arial Black",
    "subtitle_font_size": 92,
    "subtitle_karaoke": False,
    "subtitle_popin": False,
    "subtitle_colores": False,
    "subtitle_emojis": False,
    "subtitle_emoji_map": SUBTITLE_EMOJI_MAP_DEFAULT,
    "subtitle_outline": 7,
    "subtitle_margin_v": 520,
    "subtitle_palabras": 3,
    "subtitle_color": "",
    "subtitle_minusculas": False,
    "schedule_enabled": False,
    "schedule_times": ["18:00"],
    "gemini_prompt_file": "prompts/gemini_analysis.txt",
    "gpt_prompt_file": "prompts/gpt_copy.txt",
}


# También YouTube (02/11/2026): la app de Google (YT_CLIENT_ID / YT_CLIENT_SECRET, una
# sola) y el permiso de cada canal, uno por nicho (YT_REFRESH_<NICHO>). Se cargan desde
# Credenciales y viajan a GitHub por la bóveda (subir_youtube_nube.py).
_RE_SLOT_ROTACION = re.compile(
    r"^((GEMINI_API_KEY|ELEVENLABS_API_KEY)_\d+|YT_CLIENT_ID|YT_CLIENT_SECRET|YT_REFRESH_[A-Z0-9_]+)$")


def read_env() -> dict:
    data = {k: "" for k in ENV_KEYS}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            # Los slots de rotación (Gemini/ElevenLabs N) se muestran aunque no estén
            # en ENV_KEYS: así agregar una cuenta nueva desde el "+" del panel no
            # requiere tocar este archivo cada vez (a pedido de Tomix, 04/09).
            if k in data or _RE_SLOT_ROTACION.match(k):
                data[k] = v.strip()
    return data


# --- Escritura del .env ----------------------------------------------------
# Una línea del .env: "CLAVE=valor" (se tolera sangría y espacios antes del "=",
# igual que read_env). Sirve para ubicar y pisar SOLO el valor, dejando el resto
# del renglón —y del archivo— intacto.
_RE_LINEA_ENV = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")
# Nombres aceptados al guardar: los de una variable de entorno de verdad. Es el
# mismo filtro que aplica la pestaña Credenciales antes de mandar el formulario.
_RE_NOMBRE_ENV = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Si la interfaz manda estos campos vacíos se escribe el default en lugar del
# vacío: sin modelo el sistema no puede generar nada. (Lo hacía la plantilla vieja
# con `or 'gpt-4o'`; se conserva el comportamiento.)
ENV_DEFAULTS = {
    "GEMINI_MODEL": "gemini-flash-latest",
    "OPENAI_MODEL": "gpt-4o",
    "META_GRAPH_VERSION": "v21.0",
}


def _valores_a_guardar(values: dict | None) -> dict:
    """Limpia lo que llega del formulario: descarta lo que no sea una clave de
    entorno y aplasta los saltos de línea (un \\n dentro de un token partía el
    .env en dos y todo lo que venía después dejaba de leerse)."""
    out: dict[str, str] = {}
    for k, v in (values or {}).items():
        k = str(k).strip()
        if v is None or not _RE_NOMBRE_ENV.match(k):
            continue
        val = str(v).replace("\r", " ").replace("\n", " ").strip()
        out[k] = val or ENV_DEFAULTS.get(k, "")
    return out


def _backup_env() -> Path | None:
    """Copia el .env ANTES de tocarlo. NO borra ninguna copia previa: son 2 KB y
    son la única red de seguridad de las credenciales de todo el negocio. Si ya
    existe una copia idéntica de este mismo segundo, no la duplica."""
    if not ENV_PATH.exists():
        return None
    try:
        crudo = ENV_PATH.read_bytes()
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = ENV_PATH.with_name(f".env.bak_{sello}")
        n = 0
        while destino.exists() and destino.read_bytes() != crudo:
            n += 1
            destino = ENV_PATH.with_name(f".env.bak_{sello}_{n}")
        if not destino.exists():
            destino.write_bytes(crudo)
        return destino
    except OSError:
        # Un backup que falla no puede impedir que el usuario guarde su token.
        return None


def _plantilla_env(nuevos: dict) -> list[str]:
    """Esqueleto para un .env que NO existe todavía (instalación limpia). Solo se
    usa en ese caso: si el archivo ya existe jamás se reescribe entero."""
    lineas = [
        "# Editado desde la interfaz web.",
        "",
        f"GEMINI_API_KEY={nuevos.get('GEMINI_API_KEY', '')}",
        f"GEMINI_API_KEY_2={nuevos.get('GEMINI_API_KEY_2', '')}",
        f"GEMINI_API_KEY_3={nuevos.get('GEMINI_API_KEY_3', '')}",
        f"GEMINI_MODEL={nuevos.get('GEMINI_MODEL') or ENV_DEFAULTS['GEMINI_MODEL']}",
        "",
        f"OPENAI_API_KEY={nuevos.get('OPENAI_API_KEY', '')}",
        f"OPENAI_MODEL={nuevos.get('OPENAI_MODEL') or ENV_DEFAULTS['OPENAI_MODEL']}",
        "",
        f"META_APP_ID={nuevos.get('META_APP_ID', '')}",
        f"META_APP_SECRET={nuevos.get('META_APP_SECRET', '')}",
        f"META_PAGE_ACCESS_TOKEN={nuevos.get('META_PAGE_ACCESS_TOKEN', '')}",
        f"META_GRAPH_VERSION={nuevos.get('META_GRAPH_VERSION') or ENV_DEFAULTS['META_GRAPH_VERSION']}",
        "",
        f"ELEVENLABS_API_KEY={nuevos.get('ELEVENLABS_API_KEY', '')}",
        f"ELEVENLABS_API_KEY_2={nuevos.get('ELEVENLABS_API_KEY_2', '')}",
        f"ELEVENLABS_API_KEY_3={nuevos.get('ELEVENLABS_API_KEY_3', '')}",
        "",
        f"R2_BUCKET={nuevos.get('R2_BUCKET', '')}",
        f"R2_PUBLIC_BASE={nuevos.get('R2_PUBLIC_BASE', '')}",
        "",
        f"WHATSAPP_TOKEN={nuevos.get('WHATSAPP_TOKEN', '')}",
        f"WHATSAPP_PHONE_ID={nuevos.get('WHATSAPP_PHONE_ID', '')}",
        f"WHATSAPP_WABA_ID={nuevos.get('WHATSAPP_WABA_ID', '')}",
        "",
    ]
    ya = {m.group(1) for m in (_RE_LINEA_ENV.match(x) for x in lineas) if m}
    extra = [k for k, v in nuevos.items() if k not in ya and v]
    if extra:
        lineas += [f"{k}={nuevos[k]}" for k in extra] + [""]
    return lineas


def write_env(values: dict | None = None) -> None:
    """Guarda credenciales FUSIONANDO contra el .env que ya está en disco.

    Antes esta función reescribía el archivo ENTERO desde una plantilla fija de 18
    líneas, así que cualquier clave que no estuviera en esa plantilla —Hotmart,
    AD_ACCOUNT_ID, META_PAGE_ID, los Gmail, EMBUDO_TZ, ELEVEN_SYLVANA_KEY— se
    BORRABA cada vez que se apretaba "Guardar credenciales" en la web: entraban 29
    claves y salían 18. Se perdían las ventas de Hotmart, los avisos por mail y el
    responder de comentarios hasta volver a cargarlas a mano.

    Ahora se edita en el lugar: se pisa el valor de las claves que llegan y TODO lo
    demás (claves, comentarios, orden y formato) queda tal cual estaba.
    """
    nuevos = _valores_a_guardar(values)

    if not ENV_PATH.exists():
        lineas = _plantilla_env(nuevos)
    else:
        lineas = ENV_PATH.read_text(encoding="utf-8").splitlines()
        presentes: set[str] = set()
        for i, linea in enumerate(lineas):
            m = _RE_LINEA_ENV.match(linea)
            if not m:
                continue          # comentario, línea en blanco o algo raro: no se toca
            presentes.add(m.group(1))
            if m.group(1) in nuevos:
                # Se pisan TODAS las apariciones, no solo la primera: si la clave
                # estaba repetida, dotenv se queda con la última y el cambio no
                # tenía efecto. Se conserva el prefijo del renglón (sangría).
                lineas[i] = f"{linea[:m.end(1)]}={nuevos[m.group(1)]}"
        # Claves nuevas: se agregan al final. Las que llegan VACÍAS y no existían no
        # se escriben —un "CLAVE=" vacío no es lo mismo que ausente: pisa el valor
        # por defecto del código (ej. ALERT_EMAIL) y rompe el envío.
        faltantes = [k for k, v in nuevos.items() if k not in presentes and v]
        if faltantes:
            if lineas and lineas[-1].strip():
                lineas.append("")
            lineas.append("# Agregado desde la interfaz web.")
            lineas += [f"{k}={nuevos[k]}" for k in faltantes]

    texto = "\n".join(lineas)
    if not texto.endswith("\n"):
        texto += "\n"
    if ENV_PATH.exists() and ENV_PATH.read_text(encoding="utf-8") == texto:
        return                    # nada cambió: no se reescribe ni se genera backup
    _backup_env()
    # Escritura atómica: si el proceso se cae a mitad de camino, el .env viejo sigue
    # entero en disco en vez de quedar truncado (= sin credenciales).
    tmp = ENV_PATH.with_name(".env.tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ENV_PATH)


# Orden de negocio en las interfaces (topbar, Prompts, Reglas, etc.), no alfabético:
# alfabético ponía a "bonsai" primero en TODOS lados y hacía parecer que era el
# producto principal, cuando el que arrancó y tiene más nichos configurados es
# hidroponía. Pedido explícito de Tomix (29/08). Un nicho que no está en esta lista
# (uno nuevo, agregado a mano) simplemente cae al final, ordenado alfabéticamente
# entre sí — no hace falta tocar esto para que un nicho nuevo aparezca.
ORDEN_NICHOS = ["hidroponia", "bonsai", "numerologia"]


def list_niches() -> list[str]:
    nombres = sorted(p.stem for p in NICHES_DIR.glob("*.yaml"))
    def _clave(n: str):
        return (ORDEN_NICHOS.index(n) if n in ORDEN_NICHOS else len(ORDEN_NICHOS), n)
    return sorted(nombres, key=_clave)


# El nombre del nicho no es solo una etiqueta: se convierte en nombre de ARCHIVO
# (niches/<nombre>.yaml, prompts/<nombre>_gemini.txt, state/<nombre>_processed.json),
# en nombre de CARPETA (output/<nombre>, downloads/<nombre>) y en nombre de TAREA DE
# WINDOWS (AgenteMarketing_<nombre>). Venía sin validar ninguna de las tres cosas.
_RE_NOMBRE_NICHO = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")

# Reservados porque ya existen como tareas AgenteMarketing_* en la máquina: guardar la
# programación de un nicho con estos nombres ejecutaría Unregister-ScheduledTask sobre
# la tarea de producción y la borraría (los mails de boletos, el escaneo de precios,
# el recordatorio diario y la vigilancia de salud).
NOMBRES_NICHO_RESERVADOS = {
    "boletos", "precios", "precio_watch", "recordatorio", "vigilancia", "topup",
    # Y estos porque los prompts propios de un nicho se llaman prompts/<nicho>_*.txt:
    # un nicho llamado "voz" haría que su borrado se lleve puestos voz_comun.txt,
    # voz_describe.txt y voz_traducir.txt, que son los COMPARTIDOS de todos los nichos.
    "voz", "gemini", "gpt", "estructuras",
}


def normalizar_nombre_nicho(crudo: str) -> str:
    """Convierte lo que escribió la persona en un nombre usable, o lanza ValueError con
    un motivo en criollo. No 'arregla' en silencio nombres peligrosos: los rechaza."""
    n = (crudo or "").strip().lower().replace(" ", "_")
    if not n:
        raise ValueError("Escribí un nombre para el nicho.")
    # Barras, dos puntos y '..' escribirían fuera de niches/ y de prompts/.
    if not _RE_NOMBRE_NICHO.match(n):
        raise ValueError(
            "El nombre solo puede tener letras sin acento, números, guion y guion bajo, "
            "tiene que empezar con una letra y medir entre 2 y 32 caracteres. "
            f"Recibí: '{crudo}'")
    if n in NOMBRES_NICHO_RESERVADOS:
        raise ValueError(
            f"'{n}' es un nombre reservado del sistema: hay una tarea programada de "
            "Windows con ese nombre y usarlo la borraría. Elegí otro.")
    return n


def read_niche_raw(name: str) -> dict:
    path = NICHES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(name)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_niche_raw(name: str, data: dict) -> None:
    merged = dict(NICHE_FIELDS_DEFAULT)
    # El filtro por NICHE_FIELDS_DEFAULT es a propósito: evita que un formulario roto
    # llene el YAML de basura. Pero descartaba EN SILENCIO, así que agregar un campo
    # nuevo y olvidarse de sumarlo acá se veía como "no guarda" sin ningún error.
    # Agregar un campo por nicho son TRES lugares: la dataclass Niche, load_niche() y
    # NICHE_FIELDS_DEFAULT. Si falta el tercero, este aviso lo delata.
    descartados = [k for k in (data or {}) if k not in NICHE_FIELDS_DEFAULT]
    if descartados:
        logging.getLogger("marketing_agent").warning(
            "Nicho '%s': se descartaron campos desconocidos %s — si son nuevos, "
            "faltan en NICHE_FIELDS_DEFAULT (config.py).", name, descartados)
    merged.update({k: v for k, v in (data or {}).items() if k in NICHE_FIELDS_DEFAULT})
    merged["name"] = name
    for intk in ("scan_count", "top_k", "min_views", "mockup_seconds",
                 "subtitle_font_size", "subtitle_outline", "subtitle_margin_v",
                 "subtitle_palabras"):
        try:
            merged[intk] = int(merged[intk] or 0)
        except (TypeError, ValueError):
            merged[intk] = NICHE_FIELDS_DEFAULT[intk]
    try:
        merged["mockup_scale"] = float(merged["mockup_scale"])
    except (TypeError, ValueError):
        merged["mockup_scale"] = NICHE_FIELDS_DEFAULT["mockup_scale"]
    try:  # velocidad de la voz: se acota a lo que ffmpeg/ElevenLabs pueden hacer bien
        merged["voice_speed"] = max(0.5, min(3.0, float(merged["voice_speed"])))
    except (TypeError, ValueError):
        merged["voice_speed"] = NICHE_FIELDS_DEFAULT["voice_speed"]
    # Lista de slots apagados: se acepta lista o texto separado por comas (lo que manda
    # un formulario), y solo se guardan nombres de slot que existan de verdad.
    fa = merged.get("fuentes_apagadas") or []
    if isinstance(fa, str):
        fa = [x.strip() for x in fa.split(",")]
    validos = {c for c, _ in SLOTS_FUENTE}
    merged["fuentes_apagadas"] = sorted({str(x).strip() for x in fa if str(x).strip() in validos})
    for boolk in ("voiceover_when_silent", "add_mockup", "add_logo", "publish_facebook",
                  "publish_instagram", "publish_youtube", "publish_tiktok",
                  "schedule_enabled",
                  "subtitle_karaoke", "subtitle_popin", "subtitle_colores", "subtitle_emojis",
                  "subtitle_minusculas"):
        v = merged[boolk]
        merged[boolk] = v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes", "on")
    path = NICHES_DIR / f"{name}.yaml"
    path.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    subir_nicho_nube(name)


def subir_nicho_nube(name: str, esperar: bool = False) -> bool:
    """Sube niches/<name>.yaml a R2 (state/nichos/), de donde lo lee la producción de
    GitHub (r2io.bajar_nichos). Sin esto, cambiar la voz, el mockup o los subtítulos en
    el panel no llegaba a la nube (Tomix, 02/11/2026; analisis/AJUSTES_DECORACION.md).
    En segundo plano: wrangler tarda unos segundos y guardar no tiene que esperarlo."""
    import subprocess
    import threading
    path = NICHES_DIR / f"{name}.yaml"
    if not path.exists() or os.getenv("PUERTA_R2_URL"):
        return False
    resultado = {"ok": False}

    def _subir():
        try:
            p = subprocess.run(
                ["npx", "wrangler", "r2", "object", "put", f"marketing-reels/state/nichos/{name}.yaml",
                 "--file", str(path), "--content-type", "text/yaml; charset=utf-8", "--remote"],
                cwd=ROOT / "cloudflare-worker", capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120, shell=True)
            resultado["ok"] = p.returncode == 0
            if not resultado["ok"]:
                logging.getLogger("marketing_agent").warning(
                    "No subí el nicho '%s' a la nube: %s", name, (p.stderr or p.stdout)[-200:])
        except Exception as e:  # noqa: BLE001 — no subir no puede romper el guardado
            logging.getLogger("marketing_agent").warning("No subí el nicho '%s': %s", name, e)

    hilo = threading.Thread(target=_subir, daemon=True)
    hilo.start()
    if esperar:
        hilo.join()
    return resultado["ok"] if esperar else True


# Los prompts que comparten TODOS los nichos. Ninguna limpieza los puede tocar: si se
# borran, cualquier nicho que no tenga el suyo se queda sin guion de voz.
PROMPTS_COMPARTIDOS = {
    "gemini_analysis.txt", "gpt_copy.txt", "estructuras.txt", "voz_comun.txt",
    "voz_describe.txt", "voz_traducir.txt", "voz_tono.txt",
}


def delete_niche(name: str) -> None:
    # Se borran TODOS los prompts propios (prompts/<nicho>_*.txt), no solo los dos que
    # figuran en el YAML: desde que el alta copia también los de voz, quedaban seis
    # archivos huérfanos por cada nicho borrado.
    #
    # El chequeo contra PROMPTS_COMPARTIDOS es la red de seguridad del patrón <nicho>_*:
    # un nicho llamado "voz" haría que este glob matchee voz_comun.txt y compañía. El
    # validador de nombres ya lo impide, pero esto es lo que se borra: va doble candado.
    try:
        for p in (ROOT / "prompts").glob(f"{name}_*.txt"):
            if p.name not in PROMPTS_COMPARTIDOS:
                p.unlink(missing_ok=True)
    except OSError:
        pass
    (NICHES_DIR / f"{name}.yaml").unlink(missing_ok=True)
