"""
CAMINO CANÓNICO ÚNICO para publicar un reel YA PRODUCIDO.

Por qué existe
--------------
Hasta ahora había 9 lugares distintos que publicaban reels (src/pipeline.py,
programar_semana.py, postear_ganadores.py, webapp.py /api/publicar-uno y /api/publish,
programar_reel.py, _publicar_ig.py, publicar_local.py, republicar_es.py) y cada uno
escribía el historial con un formato distinto: 58 registros con 14 formas diferentes.
Peor: cada camino tenía capacidades distintas. Unos subían a YouTube y otros no; unos
mandaban el botón de WhatsApp y otros no; unos tenían el guard anti-inglés y otros no
(por eso se colaron reels en inglés a la página). Este módulo junta TODAS las
capacidades en una sola función para que no vuelva a divergir.

Este módulo NO produce el video. Sólo publica lo que ya está terminado en
output/<nicho>/<video_id>/publicar.mp4. Producir sigue siendo trabajo del pipeline.

Cómo usarlo
-----------
    from src import publisher
    rec = publisher.publicar_reel("7667515649505234198", niche, secrets)          # ahora
    rec = publisher.publicar_reel(vid, niche, secrets, when=dt)                   # programado
    rec = publisher.publicar_reel(vid, niche, secrets, dry_run=True)              # sin tocar nada
    rec = publisher.publicar_reel(vid, niche, secrets, retomar=True)              # reintentar a mano

OJO AL CONECTARLO en webapp.py: ese archivo YA tiene `from src import publish as publisher`
(webapp.py:25), o sea que ahí el nombre `publisher` significa src/publish.py. Importar este
módulo como `publisher` a secas lo pisaría y romperían las llamadas viejas. Usar un alias:
`from src import publisher as canonico`.

ESQUEMA DEL REGISTRO (lo que se escribe en state/<nicho>_processed.json)
-----------------------------------------------------------------------
Siempre las mismas claves, siempre, aunque valgan None. Los campos que ya tenía el
registro anterior y no están acá (dry_run, meta_reel_id, copy_trend…) se CONSERVAN:
no se borra historia de los 58 registros viejos.

    processed_at    str   ISO UTC "YYYY-MM-DDTHH:MM:SSZ" del último intento
    tiktok_url      str   URL de origen (informativo; viene de `extra` o del registro previo)
    views           int   vistas del original (informativo)
    title           str   título del original (informativo)
    media           str   nota de _process_media: "doblado_es+subs+mockup+logo", etc.
                          ES EL CAMPO QUE DECIDE EL GUARD ANTI-INGLÉS.
    facebook_id     str   video_id del reel de FB (publicado o programado). None si no salió.
    instagram_id    str   media_id REAL de IG (sólo cuando salió EN VIVO). None si no salió.
    instagram_queued str  URL pública en R2 del video encolado para el Worker (modo programado).
                          Ojo: encolado NO es publicado -> instagram_id queda en None.
    youtube_id      str   id del Short. None si no salió.
    publish_state   str   "SCHEDULED" si when != None; si no, el publish_state del nicho.
    scheduled_for   str   ISO local con offset (ej "2026-07-31T06:00:00-03:00") o None.
    parcial         bool  True = publicación EN CURSO (se marca ANTES de publicar).
                          Si el proceso muere, queda en True y el registro ya existe:
                          el próximo run NO vuelve a elegir el video -> nada de duplicados.
    intentos        dict  {"facebook": "ok"|"fallo"|"incierto"|"en_curso", …}. Es LA CLAVE
                          de la idempotencia: se escribe en disco ANTES de llamar a la API
                          y se corrige después. Ver "IDEMPOTENCIA" abajo.
    errores         dict  {"instagram": "motivo…"} de las plataformas que fallaron.
    publicado_por   str   "publisher.publicar_reel" (para saber qué escribió el registro).

Lo que devuelve la función es ese mismo registro MÁS tres claves que no se persisten
(CLAVES_NO_PERSISTIDAS; usar persistible() para sacarlas antes de guardar):
    ok        bool  True si salió al menos una plataforma
    saltado   str   motivo por el que no se publicó (None si se intentó publicar)
    error     str   detalle del motivo (None si no aplica)

IDEMPOTENCIA (por qué es imposible publicar dos veces)
------------------------------------------------------
Escenario real que se venía repitiendo: el proceso publica en Facebook y muere ANTES de
anotar (timeout de IG que cuelga 15 minutos, corte de luz, Ctrl-C, cuota). El registro
quedaba sin facebook_id y el siguiente run volvía a publicar el MISMO reel: duplicado en
la página, y en Instagram no hay forma de deshacerlo. Tres candados, en este orden:

  1. Se escribe el registro con parcial=True ANTES de tocar ninguna API -> el video ya
     figura en el historial y discover.find_winners() no lo vuelve a elegir.
  2. Antes de cada plataforma se persiste intentos[plataforma]="en_curso" y apenas
     vuelve la API se persiste el id (o "fallo"/"incierto"). O sea: el id de Facebook
     queda en disco ANTES de empezar la subida a Instagram, no al final de todo.
  3. Al re-correr el mismo video: si hay CUALQUIER id -> no se republica; si quedó un
     intento en "en_curso"/"incierto" -> tampoco, porque no se sabe qué salió de verdad
     (hay que mirar la página). Para forzarlo, retomar=True, y aun así sólo se reintentan
     las plataformas que NO tienen id.

Un error que la plataforma RECHAZÓ explícitamente (token vencido, 400) queda como
"fallo" y sí se puede reintentar: ahí sabemos que no se publicó nada. Un timeout o un
corte de conexión queda como "incierto": Meta pudo haberlo aceptado igual.

FORMATOS VIEJOS DEL HISTORIAL
----------------------------
Los 64 registros que ya existen tienen 15 formas distintas. Nada de esto se reescribe:
normalizar_registro() los lee a todos y devuelve el esquema de arriba. Traduce, entre
otras: meta_reel_id -> facebook_id, instagram_id="encolado:<fecha>" -> instagram_queued,
publish_state="CANCELLED_*" y cancelado=True -> cancelado, skipped -> motivo.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from config import Niche, Secrets
from src import gemini_client, publish, publish_ig, state
from src.logging_setup import get_logger
# El botón de WhatsApp sale de src/publish.py (ahí es el default). Se importa y se pasa
# EXPLÍCITO en cada llamada: si algún día alguien cambia el default del módulo, este
# camino sigue mandando el botón igual. Requisito del dueño: TODOS los reels de FB
# tienen que tener el botón.
from src.publish import WHATSAPP_CTA
# wrangler resuelto una sola vez (mismo binario que usa publish_ig para subir a R2).
from src.publish_ig import _WRANGLER

log = get_logger()

ROOT = config.ROOT

# --- Guard anti-inglés ---------------------------------------------------------
# Criterio COPIADO TAL CUAL de programar_semana.py:101 (ese funciona y ya salvó a la
# página de publicar en inglés; no se toca). El reel sólo sale si la nota de media
# EMPIEZA con uno de estos prefijos. "audio_original"/"sin_cambios"/"" = el inglés se
# coló -> no se publica.
MEDIA_ES_OK = ("doblado_es", "voz_generada_es", "audio_en_espanol")

# --- YouTube -------------------------------------------------------------------
# YT_TAGS y titulo_yt() vienen de postear_ganadores.py (líneas 28 y 31-51). Se COPIAN
# acá porque postear_ganadores.py se va a archivar: si quedaban allá, el día que se
# archive se caían también programar_semana.py y webapp.py, que los importan.
# Son específicos de hidroponía, igual que en el original: no se inventó nada nuevo.
YT_TAGS = ["hidroponia", "cultivo en casa", "huerto urbano", "aeroponia", "sin tierra", "shorts"]


def tags_yt(niche=None) -> list[str]:
    """Etiquetas del Short.

    Orden de prioridad: las del NICHO (yt_tags en su YAML) > la variable YT_TAGS del
    .env > las de siempre. Antes solo reemplazaba la PRIMERA etiqueta por el nombre del
    nicho, así que un Short de bonsái salía como "bonsai, cultivo en casa, huerto
    urbano, aeroponia, sin tierra": cuatro etiquetas de hidroponía pegadas.

    Acepta el objeto Niche o su nombre, para no romper a quien ya llamaba con el nombre.
    """
    nombre = getattr(niche, "name", niche) or "hidroponia"
    propias = list(getattr(niche, "yt_tags", None) or [])
    if propias:
        return propias
    del_env = [t.strip() for t in (os.getenv("YT_TAGS") or "").split(",") if t.strip()]
    if del_env:
        return del_env
    return [nombre] + YT_TAGS[1:]


def _tema_yt(niche=None) -> str:
    """Cómo se nombra el tema en el prompt del título ("de un video de …") y en el
    título de reserva. Sale del nicho (campo `tema`); sin eso, de NICHE_LABEL en el
    .env; sin eso, el de siempre."""
    return ((getattr(niche, "tema", "") or "").strip()
            or (os.getenv("NICHE_LABEL") or "").strip()
            or "hidroponía")


# Meta rechaza una programación demasiado cerca de "ahora". programar_reel.py:25 ya usaba
# un margen de 11 minutos por eso mismo. Se valida ANTES de subir el binario para no
# quemar una subida entera y que el error se entienda.
MARGEN_MINIMO_MIN = 10

# --- Idempotencia --------------------------------------------------------------
# Claves que PRUEBAN que el reel ya salió (o ya está encolado) en alguna plataforma.
# Si cualquiera tiene valor, republicar duplicaría el posteo.
CLAVES_ID = ("facebook_id", "instagram_id", "instagram_queued", "youtube_id")

# Las 3 claves informativas que publicar_reel() devuelve pero NO van al historial.
CLAVES_NO_PERSISTIDAS = ("ok", "saltado", "error")

# Estados de intentos[plataforma] que significan "no sé si salió" -> no se reintenta solo.
INTENTO_DUDOSO = ("en_curso", "incierto")

# Un error así puede haber llegado a Meta igual (la petición salió, la respuesta no
# volvió): el intento queda "incierto" y no se reintenta sin permiso explícito.
_SENALES_INCIERTO = ("timeout", "timed out", "connection", "conexión", "conexion",
                     "max retries", "read timed out", "broken pipe", "reset by peer",
                     "temporarily unavailable", "502", "503", "504")


def titulo_yt(descripcion: str, model: str, tema: str | None = None) -> tuple[str, str]:
    """Genera (título, hook) en español para el YouTube Short a partir de la descripción
    del video (Gemini). Fallback genérico si falla — nunca inventa datos específicos.
    COPIADO de postear_ganadores.py:31 (ver nota de YT_TAGS)."""
    tema = tema or _tema_yt()
    prompt = (f"De este análisis de un video de {tema} devolvé EXACTAMENTE dos líneas:\n"
              "TITULO: <título para YouTube Shorts en español, máx 70 caracteres, 1 emoji, terminá con #Shorts>\n"
              "HOOK: <una sola oración gancho en español>\n\n" + (descripcion or "")[:1200])
    try:
        resp = gemini_client.run(lambda c: gemini_client.generate(c, model, [prompt]))
        titulo = hook = ""
        for ln in (resp.text or "").splitlines():
            u = ln.strip().upper()
            if u.startswith("TITULO") and ":" in ln:
                titulo = ln.split(":", 1)[1].strip()
            elif u.startswith("HOOK") and ":" in ln:
                hook = ln.split(":", 1)[1].strip()
        if titulo and hook:
            return titulo, hook
    except Exception as e:  # noqa: BLE001
        log.warning("titulo_yt falló (%s), uso genérico", str(e)[:80])
    # Título de reserva. Se dispara solo, sin aviso, cuando se acaba la cuota de Gemini,
    # así que tiene que servir para CUALQUIER nicho: se arma con el tema en vez de
    # hablar de hidroponía. En español neutro, que esto lo lee el cliente.
    return (f"{tema.capitalize()} en casa desde cero 🌿 #Shorts",
            f"Aprende {tema} en casa, paso a paso 🌿")


# ==============================================================================
# Helpers
# ==============================================================================

def es_audio_espanol(media: str | None) -> bool:
    """True si la nota de media dice que el audio quedó en ESPAÑOL."""
    return bool(media) and str(media).startswith(MEDIA_ES_OK)


def normalizar_registro(rec: dict | None) -> dict:
    """Traduce CUALQUIER registro viejo del historial al esquema único (ver módulo).

    Existe porque los 64 registros que ya están en state/<nicho>_processed.json tienen
    15 formas distintas: cada uno de los 9 caminos que publicaban escribía las claves que
    le parecía. Nada se reescribe en disco (perderíamos historia); se traduce al leer.

    NUNCA lanza excepción: un registro corrupto tiene que devolver "no salió nada", no
    tumbar al que está leyendo el historial.
    """
    r = dict(rec) if isinstance(rec, dict) else {}

    fb = r.get("facebook_id") or r.get("meta_reel_id")   # meta_reel_id = nombre viejo

    # Convención vieja escrita a mano: instagram_id="encolado:<fecha>" NO es un media_id,
    # es "quedó en la cola de R2". Tomarlo por publicado hacía creer que IG ya había
    # salido cuando en realidad todavía lo tenía que publicar el Worker.
    ig = r.get("instagram_id")
    ig_cola = r.get("instagram_queued")
    sched = r.get("scheduled_for")
    if isinstance(ig, str) and ig.startswith("encolado:"):
        ig_cola = ig_cola or ig
        sched = sched or ig.split(":", 1)[1]
        ig = None

    estado = str(r.get("publish_state") or "")
    # Copias: quien lea el historial no puede terminar mutando el registro original.
    intentos = dict(r["intentos"]) if isinstance(r.get("intentos"), dict) else {}
    errores = dict(r["errores"]) if isinstance(r.get("errores"), dict) else {}

    return {
        "processed_at": r.get("processed_at"),
        "tiktok_url": r.get("tiktok_url"),
        "views": r.get("views"),
        "title": r.get("title"),
        "media": r.get("media"),
        "facebook_id": fb,
        "instagram_id": ig,
        "instagram_queued": ig_cola,
        "youtube_id": r.get("youtube_id"),
        "publish_state": r.get("publish_state"),
        "scheduled_for": sched,
        "parcial": bool(r.get("parcial")),
        "intentos": intentos,
        "errores": errores,
        "publicado_por": r.get("publicado_por"),
        # Derivados (no se persisten; son para el que lee):
        # cancelado -> lo dio de baja una persona (a mano en FB) o limpiar_cola_ig.py.
        "cancelado": bool(r.get("cancelado")) or estado.startswith("CANCELLED"),
        "publicado": bool(fb or ig or ig_cola or r.get("youtube_id")),
        "motivo": r.get("skipped") or r.get("saltado"),   # por qué no se publicó
        "dry_run": bool(r.get("dry_run")),
    }


def persistible(rec: dict) -> dict:
    """El registro SIN las 3 claves informativas (ok/saltado/error). Lo que devuelve
    publicar_reel() se puede pasar por acá antes de guardarlo, para que el historial
    quede con un solo formato."""
    return {k: v for k, v in (rec or {}).items() if k not in CLAVES_NO_PERSISTIDAS}


def _id_de(rec: dict, plataforma: str):
    """El id que prueba que ESA plataforma ya salió. Instagram tiene dos formas de
    'salió': el media_id (en vivo) y la URL encolada en R2 (programado, lo publica el
    Worker); cualquiera de las dos alcanza para no volver a mandarlo."""
    if plataforma == "instagram":
        return rec.get("instagram_id") or rec.get("instagram_queued")
    return rec.get(f"{plataforma}_id")


def _desenlace_incierto(msg: str) -> bool:
    """¿El error deja dudas de si la plataforma llegó a publicar? Un 400 con "token
    inválido" NO (no salió nada, se puede reintentar). Un timeout SÍ: la petición pudo
    haber llegado igual y reintentar duplicaría el reel."""
    m = (msg or "").lower()
    return any(s in m for s in _SENALES_INCIERTO)


def _stamp() -> str:
    """Mismo formato que pipeline._stamp(): ISO UTC con Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalizar_when(when) -> datetime | None:
    """Acepta datetime (naive u aware) o string ISO. Un datetime naive se interpreta en
    la hora LOCAL de la máquina, que es lo que venían haciendo programar_semana.py y
    programar_reel.py (datetime.now().astimezone())."""
    if when is None:
        return None
    if isinstance(when, str):
        when = datetime.fromisoformat(when)
    if when.tzinfo is None:
        return when.astimezone()
    return when


def _r2_put(local_path: Path, key: str, bucket: str, content_type: str) -> None:
    """Sube un archivo a R2 por wrangler. Copiado de programar_semana.py:29 (r2_put),
    que es el que hoy alimenta la cola del Worker."""
    cmd = (f'"{_WRANGLER}" r2 object put "{bucket}/{key}" '
           f'--file "{local_path}" --content-type {content_type} --remote')
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f"R2 put falló ({key}): {(p.stderr or p.stdout)[-250:]}")


def _r2_existe(bucket: str, key: str) -> bool | None:
    """True/False si el objeto existe en R2. None = NO DETERMINABLE (wrangler no está,
    no hay red, no hay credenciales). El que llama tiene que tratar None como 'no sé',
    nunca como 'no existe'.

    Ojo: wrangler contesta "The specified key does not exist." TANTO si falta la key
    como si el bucket está mal escrito (comprobado). O sea que False significa "no está
    ahí", sin distinguir el motivo. No importa para lo que se usa: si el bucket
    estuviera mal, el put posterior falla ruidosamente y no se pisa nada.
    """
    try:
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "r2check.bin"
            cmd = (f'"{_WRANGLER}" r2 object get "{bucket}/{key}" '
                   f'--file "{destino}" --remote')
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=90)
            if p.returncode == 0:
                return True
            salida = f"{p.stdout} {p.stderr}".lower()
            # 404 / "not found" / "does not exist" = respuesta legítima: no está.
            if any(t in salida for t in ("404", "not found", "does not exist",
                                         "no such", "notfound")):
                return False
            return None
    except Exception as e:  # noqa: BLE001
        log.warning("No pude consultar R2 (%s): %s", key, str(e)[:120])
        return None


def _r2_leer_json(bucket: str, key: str):
    """El contenido de un objeto de R2 ya parseado, o None si no está / no se puede leer.
    None significa "no sé", nunca "está vacío"."""
    try:
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "r2.json"
            cmd = (f'"{_WRANGLER}" r2 object get "{bucket}/{key}" '
                   f'--file "{destino}" --remote')
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)
            if p.returncode != 0 or not destino.is_file():
                return None
            return json.loads(destino.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("No pude leer %s de R2: %s", key, str(e)[:120])
        return None


# Cuántos reels como máximo por día EN LA MISMA CUENTA de Instagram. El límite real no es
# la fecha sino la cuenta: dos nichos publican en cuentas distintas y no se estorban.
# Dos alcanza para la prueba A/B del mismo día; más que eso empieza a cansar al público.
IG_MAX_POR_CUENTA_POR_DIA = int(os.getenv("IG_MAX_POR_CUENTA_POR_DIA") or 2)


def _cola_ig_jobs(datestr: str, bucket: str) -> list:
    """Los trabajos que ya hay encolados para esa fecha. Un archivo puede tener uno solo
    (formato viejo) o una lista."""
    if not bucket:
        return []
    d = _r2_leer_json(bucket, f"queue/{datestr}.json")
    if d is None:
        return []
    return d if isinstance(d, list) else [d]


def _cola_ig_ocupada(datestr: str, video_id: str, bucket: str) -> str | None:
    """Devuelve el id del reel que YA ocupa queue/<datestr>.json, o None si está libre.

    Por qué importa: el Worker (cloudflare-worker/src/index.js:2491) lista queue/ y se
    queda con el PRIMER key que cumpla `k <= queue/<hoy>.json`, lee UN job del archivo y
    después borra el key. O sea: un archivo = un reel. Si se pisara el archivo de una
    fecha, el reel que ya estaba encolado desaparece sin aviso. Por eso acá NO se pisa:
    se avisa con un error claro.

    Se pregunta PRIMERO a R2, que es lo único que el Worker mira de verdad. Si R2 no se
    puede consultar (sin wrangler, sin red), se cae al historial local: es una
    aproximación, porque un job ya publicado deja el `instagram_queued` puesto en el
    registro aunque el Worker ya haya borrado el archivo.
    """
    if bucket:
        existe = _r2_existe(bucket, f"queue/{datestr}.json")
        if existe is True:
            return f"queue/{datestr}.json ya está en R2"
        if existe is False:
            return None   # R2 manda: la fecha está libre

    try:
        for f in sorted(state.STATE_DIR.glob("*_processed.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            for vid, crudo in (data or {}).items():
                if vid == video_id:
                    continue
                # normalizar_registro() se hace cargo de los formatos viejos (entre ellos
                # instagram_id="encolado:<fecha>", que es una cola y no un media_id).
                rec = normalizar_registro(crudo)
                # Los cancelados ya no ocupan: limpiar_cola_ig.py les borra el archivo de
                # R2 pero les deja el instagram_queued puesto en el registro.
                if rec["cancelado"]:
                    continue
                if rec["instagram_queued"] and str(rec["scheduled_for"] or "")[:10] == datestr:
                    return vid
    except Exception as e:  # noqa: BLE001
        log.warning("No pude revisar el historial para la cola IG: %s", str(e)[:120])
    return None


def _resolver_niche(niche) -> Niche:
    """Acepta el objeto Niche o el nombre del nicho, para que ningún caller tenga que
    cargarlo dos veces."""
    if isinstance(niche, str):
        return config.load_niche(niche)
    return niche


def _salida(rec: dict, ok: bool, saltado: str | None = None, error: str | None = None) -> dict:
    """Registro + las 3 claves informativas que NO se persisten."""
    out = dict(rec)
    out["ok"] = ok
    out["saltado"] = saltado
    out["error"] = error
    return out


def _guardar(niche_name: str, video_id: str, rec: dict) -> None:
    """Vuelca el registro a disco YA. Se llama antes y después de CADA plataforma: si el
    proceso muere en la mitad, lo que ya salió queda anotado igual (antes se escribía una
    sola vez al final y un timeout de Instagram se llevaba puesto el id de Facebook)."""
    state.mark_processed(niche_name, video_id, persistible(rec))


# ==============================================================================
# La función
# ==============================================================================

def con_origen(texto: str, plataforma: str, video_id: str) -> str:
    """Le cuelga el origen (`sck` de Hotmart) a los links de compra que haya en el copy.

    POR QUÉ ACÁ Y NO AL GENERAR EL COPY
    El mismo copy_final.txt se publica en Facebook Y en Instagram. Si se etiquetara al
    generarlo, las dos redes compartirían el código y no habría forma de saber cuál
    vendió. Etiquetando al publicar, cada red se lleva el suyo.

    Se etiqueta POR VIDEO (`ig|r|<id>`), no solo por red: así se sabe QUÉ reel vendió,
    que es lo que decide si conviene repetir ese tipo de contenido. Y como el id es el
    mismo en las tres plataformas, un video se puede comparar entre ellas.

    Reglas de Hotmart (ver config.sck): 30 caracteres, sin guión bajo, separador "|".
    Romperlas no da error: Hotmart descarta el código y la venta queda sin origen.
    """
    if not texto:
        return texto
    try:
        origen = config.sck(plataforma, "r", str(video_id))
        etiquetado = config.checkout(None, origen)
        base = config.checkout()
        if not base or not etiquetado or base == etiquetado:
            return texto
        # Solo se toca el link que YA está en el texto: no se agrega ninguno.
        return texto.replace(base, etiquetado)
    except Exception:  # noqa: BLE001
        log.warning("No pude etiquetar el origen del copy (%s/%s); va sin etiqueta.",
                    plataforma, video_id)
        return texto


def publicar_reel(video_id: str, niche, secrets: Secrets | None = None,
                  when=None, copy: str | None = None,
                  media: str | None = None, extra: dict | None = None,
                  dry_run: bool = False, retomar: bool = False) -> dict:
    """Publica (o programa) UN reel ya producido en Facebook + Instagram + YouTube.

    video_id : carpeta del reel dentro de output/<nicho>/.
    niche    : objeto config.Niche (o el nombre del nicho).
    secrets  : config.Secrets. Si es None se cargan solos.
    when     : None = publicar AHORA. datetime (o ISO) = PROGRAMAR para esa hora.
    copy     : texto del posteo. None = se lee output/<nicho>/<id>/copy_final.txt.
    media    : nota de audio del video ("doblado_es+subs…"). Sólo hace falta cuando el
               video TODAVÍA no está en el historial (recién producido por el pipeline):
               el guard anti-inglés necesita saber en qué idioma quedó el audio. Si no
               se pasa y tampoco está en el historial, NO se publica (no se adivina).
    extra    : campos informativos del descubrimiento (tiktok_url, views, title) para
               el registro. Opcional.
    dry_run  : valida TODO (video, guard, idempotencia, cola de IG) y devuelve el
               registro que escribiría, pero no toca Meta/YouTube/R2 ni el historial.
    retomar  : SOLO para arreglar a mano una publicación que quedó a medias. Reintenta
               las plataformas que NO tienen id, aunque el intento anterior haya quedado
               dudoso. Antes de usarlo hay que MIRAR la página: si aquel intento sí había
               salido, esto duplica el reel.

    Nunca lanza excepción por un fallo de plataforma: cada red va en su propio
    try/except y lo que no salió queda anotado en rec["errores"].
    """
    niche = _resolver_niche(niche)
    secrets = secrets or config.load_secrets()
    video_id = str(video_id)
    when = _normalizar_when(when)

    out_dir = ROOT / "output" / niche.name / video_id
    mp4 = out_dir / "publicar.mp4"

    # crudo = lo que hay en disco tal cual (se conserva entero para no perder historia).
    # prev  = lo mismo traducido al esquema único: es lo ÚNICO que se mira para decidir.
    crudo = dict(state.load_processed(niche.name).get(video_id) or {})
    prev = normalizar_registro(crudo)

    # Base informativa: lo que ya había + lo que trae el caller. Se devuelve en TODOS los
    # cortes tempranos (falta el mp4, guard, etc.) para que quien reciba un "saltado"
    # pueda anotarlo con el MISMO formato y no invente el suyo, que es exactamente lo que
    # generó los 15 formatos distintos del historial.
    base = dict(crudo)
    base.update(extra or {})
    if media is not None:
        base["media"] = media

    # --- 1. El video producido tiene que existir --------------------------------
    # SIEMPRE publicar.mp4, NUNCA el crudo de downloads/: ese está en inglés y sin
    # editar (sin doblaje, sin subtítulos, sin mockup ni logo). Publicarlo mandaba a la
    # página un video en otro idioma y sin marca.
    if not mp4.is_file():
        log.error("No existe %s -> no hay nada que publicar (el crudo de downloads/ "
                  "NO se publica nunca).", mp4)
        return _salida(base, False, "falta_publicar_mp4", str(mp4))

    # --- 2. Idempotencia: ¿ya salió? --------------------------------------------
    # Mismo criterio que webapp.py:1045 pero mirando también instagram_queued (encolado
    # ES publicado: lo saca el Worker) y los nombres viejos (meta_reel_id,
    # instagram_id="encolado:…"), que antes se leían como "no salió nada" y republicaban.
    # Republicar duplica el reel en la página y en IG no hay forma de deshacerlo.
    ya = {k: prev[k] for k in CLAVES_ID if prev[k]}
    if ya and not retomar:
        log.info("%s ya estaba publicado (%s) -> no se republica.", video_id,
                 ", ".join(f"{k}={v}" for k, v in ya.items()))
        return _salida(base, True, "ya_publicado")

    # --- 2b. Idempotencia: ¿quedó un intento sin desenlace? ---------------------
    # El caso que rompía todo: se publicó en Facebook y el proceso murió antes de anotar.
    # En disco queda intentos={"facebook":"en_curso"} y facebook_id=None. Volver a
    # intentar sería publicarlo DOS VECES, así que se frena y se avisa. Lo resuelve una
    # persona mirando la página (retomar=True si de verdad no salió).
    dudosos = {p: e for p, e in prev["intentos"].items()
               if e in INTENTO_DUDOSO and not _id_de(prev, p)}
    if dudosos and not retomar:
        detalle = ", ".join(f"{p}={e}" for p, e in dudosos.items())
        log.error("%s tiene un intento anterior SIN CONFIRMAR (%s). No se reintenta solo: "
                  "mirá la página y, si no salió, corré con retomar=True.", video_id, detalle)
        return _salida(base, False, "intento_sin_confirmar", detalle)

    # --- 3. Guard anti-inglés ---------------------------------------------------
    nota_media = media if media is not None else prev["media"]
    if not es_audio_espanol(nota_media):
        log.error("GUARD anti-inglés: media='%s' no es español -> NO se publica %s",
                  nota_media, video_id)
        # A propósito NO se escribe el historial: si se marcara acá, el video quedaría
        # inutilizable para siempre. Así se puede re-doblar y reintentar.
        return _salida(base, False, "guard_anti_ingles",
                       f"media={nota_media!r} (esperaba {MEDIA_ES_OK})")

    # --- 4. Copy ----------------------------------------------------------------
    copy_f = out_dir / "copy_final.txt"
    if copy is None:
        copy = copy_f.read_text(encoding="utf-8").strip() if copy_f.is_file() else ""
    else:
        copy = (copy or "").strip()
        if copy and not dry_run:
            # El copy que se publica queda guardado en disco, igual que hace hoy
            # webapp.py /api/publish: si no, el archivo miente sobre lo que salió.
            copy_f.parent.mkdir(parents=True, exist_ok=True)
            copy_f.write_text(copy, encoding="utf-8")
    if not copy:
        log.error("No hay copy para %s (ni parámetro ni copy_final.txt).", video_id)
        return _salida(base, False, "sin_copy", str(copy_f))

    # --- 5. Programación --------------------------------------------------------
    ts = None
    datestr = None
    publish_at_utc = None
    if when is not None:
        limite = datetime.now(timezone.utc) + timedelta(minutes=MARGEN_MINIMO_MIN)
        if when.astimezone(timezone.utc) <= limite:
            log.error("La hora pedida (%s) está a menos de %d minutos: Meta la rechaza.",
                      when.isoformat(), MARGEN_MINIMO_MIN)
            return _salida(base, False, "when_muy_cerca", when.isoformat())
        ts = int(when.timestamp())
        datestr = when.strftime("%Y-%m-%d")
        publish_at_utc = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- 6. Registro "EN CURSO" ANTES de publicar -------------------------------
    # Patrón de postear_ganadores.py:135. Si el proceso muere en la mitad (timeout de
    # IG, corte de luz, cuota), el video YA figura en el historial y el próximo run no
    # lo vuelve a elegir. Sin esto se publicaba dos veces el mismo reel.
    rec = dict(base)                       # conserva campos históricos (dry_run, meta_reel_id…)
    rec.update(extra or {})
    for k in ("tiktok_url", "views", "title"):
        rec.setdefault(k, None)
    intentos_prev = dict(prev["intentos"])
    rec.update({
        "processed_at": _stamp(),
        "media": nota_media,
        "publish_state": "SCHEDULED" if when else niche.publish_state,
        "scheduled_for": when.isoformat() if when else prev["scheduled_for"],
        # Los ids salen del registro NORMALIZADO: así un meta_reel_id viejo queda como
        # facebook_id y no se lo republica por leerlo con el nombre nuevo.
        "facebook_id": prev["facebook_id"],
        "instagram_id": prev["instagram_id"],
        "instagram_queued": prev["instagram_queued"],
        "youtube_id": prev["youtube_id"],
        "parcial": True,
        # copia: intentos_prev queda intacto para poder comparar contra lo que había
        # antes de esta corrida (lo usa _arrancar para decidir si reintenta).
        "intentos": dict(intentos_prev),
        "errores": {},
        "publicado_por": "publisher.publicar_reel",
    })
    if dry_run:
        # El único chequeo remoto que igual se hace es el de la cola de IG: es de sólo
        # lectura y es lo que más conviene saber ANTES de producir un reel para una fecha.
        if when and niche.publish_instagram:
            ocupa = _cola_ig_ocupada(datestr, video_id, secrets.r2_bucket)
            if ocupa:
                rec["errores"] = {"instagram": f"la cola de {datestr} ya está ocupada ({ocupa})"}
        log.info("[DRY-RUN] %s listo para publicar (media=%s, when=%s). No se toca nada.",
                 video_id, nota_media, when.isoformat() if when else "ahora")
        rec["parcial"] = False
        return _salida(rec, True, "dry_run")
    _guardar(niche.name, video_id, rec)

    errores: dict[str, str] = {}

    def _arrancar(plataforma: str) -> bool:
        """Deja anotado EN DISCO que se va a llamar a esa plataforma, y dice si hay que
        seguir. El orden importa: primero el disco, después la API. Si el proceso muere
        durante la llamada, el 'en_curso' queda y el próximo run no republica a ciegas."""
        if intentos_prev.get(plataforma) in INTENTO_DUDOSO and not retomar:
            errores[plataforma] = (f"intento anterior sin confirmar "
                                   f"({intentos_prev[plataforma]}): revisar a mano")
            log.error("%s: %s quedó sin confirmar antes -> no se reintenta solo.",
                      video_id, plataforma)
            return False
        rec["intentos"][plataforma] = "en_curso"
        _guardar(niche.name, video_id, rec)
        return True

    def _ok(plataforma: str, clave_id: str, valor) -> None:
        """La plataforma respondió bien: id a disco YA (no al final de todo)."""
        rec[clave_id] = valor
        rec["intentos"][plataforma] = "ok"
        _guardar(niche.name, video_id, rec)

    def _fallo(plataforma: str, e: Exception) -> None:
        """La plataforma falló. Si el error deja dudas (timeout, conexión cortada) queda
        'incierto' y NO se reintenta solo: pudo haberse publicado igual."""
        msg = str(e)[:300]
        errores[plataforma] = msg
        rec["intentos"][plataforma] = "incierto" if _desenlace_incierto(msg) else "fallo"
        rec["errores"] = dict(errores)
        _guardar(niche.name, video_id, rec)

    # --- 7. Facebook ------------------------------------------------------------
    # Cada plataforma en su propio try/except: que falle una no puede tumbar a las otras
    # (antes, un timeout de IG dejaba a YouTube sin subir aunque FB ya hubiera salido).
    if not niche.publish_facebook:
        log.info("Facebook desactivado en el nicho -> se omite.")
    elif rec.get("facebook_id"):
        log.info("Facebook ya tenía id (%s) -> no se republica.", rec["facebook_id"])
    elif _arrancar("facebook"):
        try:
            fb_id = publish.publish_reel(
                video_path=mp4, description=con_origen(copy, "fb", video_id),
                page_id=niche.meta_page_id,
                page_token=config.token_de_pagina(niche.meta_page_id, secrets),
                graph_version=secrets.meta_graph_version,
                video_state="SCHEDULED" if when else niche.publish_state,
                scheduled_publish_time=ts,
                call_to_action=WHATSAPP_CTA)   # botón WhatsApp SIEMPRE
            _ok("facebook", "facebook_id", fb_id)
            log.info("Facebook %s -> %s", "programado" if when else "OK", fb_id)
        except Exception as e:  # noqa: BLE001
            _fallo("facebook", e)
            log.warning("Facebook falló (siguen IG/YouTube): %s", str(e)[:150])

    # --- 8. Instagram -----------------------------------------------------------
    if not niche.publish_instagram:
        log.info("Instagram desactivado en el nicho -> se omite.")
    elif _id_de(rec, "instagram"):
        # Ya había un job encolado (o un media_id) para este video: encolarlo de nuevo
        # pisaría el archivo de otra fecha o duplicaría el reel.
        log.info("Instagram ya estaba publicado/encolado (%s) -> no se vuelve a mandar.",
                 _id_de(rec, "instagram"))
    elif when is None:
        # EN VIVO. IG no tiene borradores ni programación por API: media_publish sale ya.
        if niche.publish_state != "PUBLISHED":
            log.info("Instagram no soporta %s por API -> se omite.", niche.publish_state)
            errores["instagram"] = f"publish_state={niche.publish_state} no sale por API"
        elif _arrancar("instagram"):
            try:
                # El token de ESTA página, no el global: con varios nichos el guardado
                # en el .env es el de una sola y las demás fallan por permisos.
                ptok = config.token_de_pagina(niche.meta_page_id, secrets)
                ig_user = publish_ig.get_ig_user_id(niche.meta_page_id, ptok,
                                                    secrets.meta_graph_version)
                if not ig_user:
                    raise RuntimeError("La página no tiene Instagram vinculado.")
                ig_id = publish_ig.publish_reel_ig(
                    mp4, con_origen(copy, "ig", video_id), ig_user, ptok,
                    secrets.r2_bucket, secrets.r2_public_base, secrets.meta_graph_version)
                _ok("instagram", "instagram_id", ig_id)
                log.info("Instagram OK -> %s", ig_id)
            except Exception as e:  # noqa: BLE001
                _fallo("instagram", e)
                log.warning("Instagram falló (sigue YouTube): %s", str(e)[:150])
    elif _arrancar("instagram"):
        # PROGRAMADO -> cola en R2 que publica el Worker de Cloudflare (sin la PC prendida).
        try:
            # La clave sigue siendo queue/<fecha>.json EXACTA: el nombre del archivo es
            # el reloj del Worker (filtra con `k <= queue/<hoy>.json`), así que un sufijo
            # por nicho jamás vencería. Lo que cambió es el CONTENIDO: ahora el archivo
            # tiene una LISTA y cada trabajo dice a qué Instagram va.
            ig_destino = publish_ig.get_ig_user_id(
                niche.meta_page_id, config.token_de_pagina(niche.meta_page_id, secrets),
                secrets.meta_graph_version)
            if not ig_destino:
                raise RuntimeError("La página del nicho no tiene Instagram vinculado.")

            jobs = _cola_ig_jobs(datestr, secrets.r2_bucket)
            # Idempotencia: si este mismo video ya está en la lista, no se duplica.
            if any(j.get("tiktok_id") == video_id for j in jobs):
                raise RuntimeError(f"Este reel ya estaba encolado para {datestr}.")
            # SIN TOPE (31/08, orden directa de Tomix): antes acá se cortaba a las 2
            # colas por cuenta por día. No lo pidió nadie, lo sacó.
            video_key = f"reels/{video_id}.mp4"
            _r2_put(mp4, video_key, secrets.r2_bucket, "video/mp4")
            ig_url = f"{secrets.r2_public_base.rstrip('/')}/{video_key}"
            # publish_at: sin esto el Worker publicaba por FECHA nomás y el reel salía a
            # la hora del cron, no a la hora elegida.
            job = {"r2_url": ig_url, "caption": con_origen(copy, "ig", video_id),
                   "video_key": video_key,
                   "date": datestr, "tiktok_id": video_id, "publish_at": publish_at_utc,
                   # A qué cuenta va y de qué nicho es. Sin esto todos los reels de todos
                   # los nichos salían en el Instagram configurado en el Worker.
                   "ig_user_id": ig_destino, "nicho": niche.name}
            # RELEE justo antes de escribir (30/08, race real encontrada): "jobs" se leyó
            # ANTES de subir el video (_r2_put de arriba, que puede tardar). En ese hueco,
            # el Worker de Cloudflare corre su propio cron cada 10 min y puede haber
            # agregado OTRO trabajo (ej. el sistema de stock publicando las 18h) al MISMO
            # archivo. Escribir la lista vieja lo pisaba sin dejar rastro — la publicación
            # de Instagram de esa hora desaparecía sin ningún error en ningún lado.
            # Releer ahora, justo antes de escribir, cierra ese hueco.
            jobs = _cola_ig_jobs(datestr, secrets.r2_bucket)
            if any(j.get("tiktok_id") == video_id for j in jobs):
                raise RuntimeError(f"Este reel ya estaba encolado para {datestr} (detectado al releer).")
            jobs.append(job)
            qfile = out_dir / f"queue_{datestr}.json"
            qfile.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            _r2_put(qfile, f"queue/{datestr}.json", secrets.r2_bucket, "application/json")
            _ok("instagram", "instagram_queued", ig_url)
            log.info("Instagram encolado para %s (R2) -> cuenta %s · %d en esa fecha.",
                     datestr, ig_destino, len(jobs))
        except Exception as e:  # noqa: BLE001
            _fallo("instagram", e)
            log.warning("Instagram no quedó encolado (siguen FB/YouTube): %s", str(e)[:200])

    # --- 9. YouTube -------------------------------------------------------------
    if not niche.publish_youtube:
        log.info("YouTube desactivado en el nicho -> se omite.")
    elif rec.get("youtube_id"):
        log.info("YouTube ya tenía id (%s) -> no se resube.", rec["youtube_id"])
    elif _arrancar("youtube"):
        try:
            from subir_youtube import publish_short
            desc_f = out_dir / "descripcion_gemini.txt"
            desc = desc_f.read_text(encoding="utf-8") if desc_f.is_file() else copy
            titulo, hook = titulo_yt(desc, secrets.gemini_model, _tema_yt(niche))
            # El nicho tiene que viajar: de él salen el LINK DE COMPRA de la descripción
            # y del comentario fijado. Sin esto, el Short de un nicho vendía el de otro.
            yt_id = publish_short(mp4, titulo, hook, tags_yt(niche),
                                  publish_at=publish_at_utc, nicho=niche.name)
            _ok("youtube", "youtube_id", yt_id)
            log.info("YouTube %s -> https://youtube.com/shorts/%s",
                     "programado" if when else "OK", yt_id)
        except Exception as e:  # noqa: BLE001
            _fallo("youtube", e)
            log.warning("YouTube falló (FB/IG no se tocan): %s", str(e)[:150])

    # --- 10. TikTok -------------------------------------------------------------
    if niche.publish_tiktok:
        # La API de TikTok necesita auditoría aprobada. Se deja anotado para que el
        # toggle no mienta: el video igual queda producido en disco.
        errores["tiktok"] = "API de TikTok sin auditoría aprobada"
        log.warning("TikTok activado pero la API todavía no está aprobada -> se omite. "
                    "El video queda en %s", mp4)

    # --- 11. Registro final -----------------------------------------------------
    rec["errores"] = errores
    rec["parcial"] = False
    rec["processed_at"] = _stamp()
    _guardar(niche.name, video_id, rec)

    salio = any(rec.get(k) for k in CLAVES_ID)
    if salio:
        log.info("Listo %s: fb=%s ig=%s ig_cola=%s yt=%s%s", video_id,
                 rec["facebook_id"], rec["instagram_id"], rec["instagram_queued"],
                 rec["youtube_id"], f"  errores={list(errores)}" if errores else "")
        _avisar_reel(niche.name, video_id, rec, when, errores, copy)
    else:
        log.error("%s NO salió en ninguna plataforma: %s", video_id, errores)
    return _salida(rec, salio, None if salio else "sin_plataformas",
                   None if salio else json.dumps(errores, ensure_ascii=False))


def _avisar_reel(nicho: str, video_id: str, rec: dict, when, errores: dict,
                 copy: str) -> None:
    """WhatsApp + mail cada vez que un reel se publica o se programa con éxito en
    alguna red. Vive ACÁ (no en webapp.py ni en un script aparte) para que dispare
    SIEMPRE que se llama a publicar_reel — panel, tarea programada, CLI o el pipeline
    solo — sin depender de que alguien esté mirando ni de que Claude esté corriendo.
    Un aviso por reel, nunca lanza excepción (si falla, no debe tumbar la publicación)."""
    try:
        from src import notify
        redes = []
        if rec.get("facebook_id"):
            redes.append(f"📘 Facebook: {rec['facebook_id']}")
        if rec.get("instagram_id"):
            redes.append(f"📸 Instagram: {rec['instagram_id']}")
        elif rec.get("instagram_queued"):
            redes.append(f"📸 Instagram: encolado ({rec['instagram_queued']})")
        if rec.get("youtube_id"):
            redes.append(f"▶️ YouTube: https://youtube.com/shorts/{rec['youtube_id']}")
        if errores:
            redes.append("⚠️ Sin salir: " + ", ".join(errores.keys()))
        cuando_txt = when.strftime("%d/%m/%Y %H:%M") if when else "ahora"
        copy_txt = (copy or "").strip()
        asunto = f"Reel {'programado' if when else 'publicado'} ({nicho}): {video_id}"
        cuerpo = (
            f"Nicho: {nicho}\nVideo: {video_id}\nCuándo: {cuando_txt}\n\n"
            + "\n".join(redes) + "\n\n--- COPY ---\n" + (copy_txt or "(sin copy)")
        )
        notify.whatsapp(asunto, cuerpo)
    except Exception as e:  # noqa: BLE001
        log.warning("No pude mandar el aviso de reel publicado (%s): %s",
                    video_id, str(e)[:150])


# ==============================================================================
# CLI de verificación. Por defecto NO publica: hay que pedirlo con --publicar.
#   python -m src.publisher hidroponia 7667515649505234198
#   python -m src.publisher hidroponia 7667515649505234198 --publicar
# ==============================================================================
def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Publica un reel ya producido (camino canónico).")
    ap.add_argument("niche")
    ap.add_argument("video_id")
    ap.add_argument("--when", default=None, help='ISO local, ej "2026-08-02T18:00:00"')
    ap.add_argument("--publicar", action="store_true",
                    help="publica de verdad (sin esto es dry-run)")
    ap.add_argument("--retomar", action="store_true",
                    help="reintenta las plataformas SIN id de una publicación que quedó "
                         "a medias. MIRÁ la página antes: si aquello sí salió, duplica.")
    a = ap.parse_args()
    rec = publicar_reel(a.video_id, a.niche, None, when=a.when,
                        dry_run=not a.publicar, retomar=a.retomar)
    print(json.dumps(rec, ensure_ascii=False, indent=2, default=str))
    return 0 if rec.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_main())
