#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sube los reels a YouTube (Shorts) vía YouTube Data API v3.
   OAuth una sola vez (abre el navegador, guarda youtube_token.json).
   Requiere client_secret.json (App de escritorio) en esta carpeta.

   python subir_youtube.py           # sube los 4
   python subir_youtube.py 0         # sube solo el índice 0 (el de 41M)
"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CLIENT = BASE / "client_secret.json"
TOKEN = BASE / "youtube_token_full.json"   # scope amplio: subir + comentar + editar
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def _nicho() -> str:
    """Nicho activo. OJO con os.getenv("NICHE", "hidroponia"): el default NO se usa
    cuando la variable EXISTE pero está VACÍA (NICHE= en el .env) y load_niche("")
    revienta -> el Short se sube con el checkout en blanco. Con `or`, una variable
    vacía o con espacios se comporta igual que no tenerla."""
    return (os.getenv("NICHE") or "").strip() or "hidroponia"


NICHO = _nicho()


def _checkout() -> str:
    """El link de venta sale del NICHO (cta_link), no del código: así el sistema es
    replicable por otro usuario/producto sin tocar nada."""
    try:
        import config
        return config.load_niche(NICHO).cta_link
    except Exception:
        return ""


CHECKOUT = _checkout()


def _nicho_de(nicho=None) -> str:
    """El nicho del video que se está subiendo, no el de la variable de entorno.

    NICHO se congela al IMPORTAR el módulo desde os.getenv("NICHE"), así que con más de
    un nicho el Short de bonsái salía con la descripción, los hashtags y —lo grave— el
    LINK DE COMPRA de hidroponía. Plata yendo al producto equivocado, sin ningún error.
    Ahora el nicho viaja como parámetro; sin él se comporta como siempre.
    """
    return (nicho or "").strip() or NICHO


def _checkout_de(video_path=None, nicho=None) -> str:
    """El link de venta CON el origen puesto (parámetro `sck` de Hotmart).

    Se etiqueta POR VIDEO, no solo "vino de YouTube": así se sabe QUÉ Short vendió, que
    es lo que decide si conviene repetir ese tipo de contenido. El id sale de la carpeta
    del reel (output/<nicho>/<id>/publicar.mp4) — el mismo id con el que se publica en
    Instagram y Facebook, así el mismo video se puede comparar entre plataformas.
    """
    import pathlib as _pl
    try:
        import config
        rid = _pl.Path(str(video_path)).parent.name if video_path else ""
        return config.checkout(_nicho_de(nicho), config.sck("yt", rid) if rid else "yt")
    except Exception:
        return CHECKOUT


def _campo(nicho, campo, por_defecto=""):
    """Un campo del YAML del nicho, con red por si el nicho no existe."""
    try:
        import config
        return getattr(config.load_niche(_nicho_de(nicho)), campo, "") or por_defecto
    except Exception:
        return por_defecto


def comentario(video_path=None, nicho=None) -> str:
    tema = _campo(nicho, "tema", "hidroponía")
    return (f"🌱 ¿Quieres aprender {tema} desde cero? Curso completo "
            f"👉 {_checkout_de(video_path, nicho)}")


COMMENT = comentario()
# Hashtags del Short. Salen del nicho (yt_hashtags); si el nicho no los define se usa
# YT_HASHTAGS del .env y, sin eso, los de siempre. No se toca lo que ya está publicando.
HASHTAGS_DEFAULT = (os.getenv("YT_HASHTAGS") or "").strip() \
    or "#hidroponia #cultivoencasa #huertourbano #aeroponia #jardineria #Shorts"
HASHTAGS = HASHTAGS_DEFAULT   # compatibilidad con los scripts sueltos que lo importan


def hashtags_de(nicho=None) -> str:
    return _campo(nicho, "yt_hashtags", HASHTAGS_DEFAULT)


def desc(hook, video_path=None, nicho=None):
    # En español neutro: esto lo lee el cliente, y se vende en toda Latinoamérica.
    producto = _campo(nicho, "producto_nombre", "") \
        or f"armar tu huerto hidropónico desde cero"
    return (f"{hook}\n\n"
            f"👉 Aprende con el curso completo: {producto}\n"
            f"{_checkout_de(video_path, nicho)}\n\n"
            f"{hashtags_de(nicho)}")


# Lista histórica de 4 videos concretos (se usa con `python subir_youtube.py [indice]`).
# La carpeta sale del nicho activo: con el default apunta a output/hidroponia, igual que
# siempre. El pipeline normal NO pasa por acá, usa publish_short().
VIDEOS = [
    {"path": f"output/{NICHO}/7455638975789813025/publicar.mp4",
     "title": "Cómo cultivar lechugas SIN tierra en casa 🥬 #Shorts",
     "hook": "Estas lechugas crecen sin una sola gota de tierra, en menos de 1 m² 🤯 Frescas todo el año, sin pesticidas y con 90% menos agua.",
     "tags": ["hidroponia", "cultivo en casa", "huerto urbano", "lechugas", "aeroponia", "jardineria"]},
    {"path": f"output/{NICHO}/7507576587345235222/publicar.mp4",
     "title": "De la semilla a la cosecha: lechuga hidropónica 🌱 #Shorts",
     "hook": "Así crece una lechuga hidropónica de la semilla a la cosecha 🌱 Sin tierra, en cualquier espacio.",
     "tags": ["hidroponia", "lechuga", "cultivo en casa", "huerto", "aeroponia"]},
    {"path": f"output/{NICHO}/7647880082932960534/publicar.mp4",
     "title": "Así funciona una granja vertical hidropónica 🌿 #Shorts",
     "hook": "Detrás de escena de una granja vertical: cientos de plantas creciendo en torres, sin tierra 🌿",
     "tags": ["hidroponia", "granja vertical", "aeroponia", "agricultura", "cultivo en casa"]},
    {"path": f"output/{NICHO}/7612982494161407254/publicar.mp4",
     "title": "Cultivar apio en torres hidropónicas 🥬 #Shorts",
     "hook": "Apio fresco cultivado en torres hidropónicas, sin tierra y en poco espacio 🥬",
     "tags": ["hidroponia", "apio", "cultivo en casa", "huerto urbano", "aeroponia"]},
]


def get_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT.exists():
                print("❌ Falta client_secret.json en marketing-agent/ (App de escritorio de Google Cloud)."); sys.exit(2)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
            creds = flow.run_local_server(
                port=8765, open_browser=True,
                authorization_prompt_message="\n👉 AUTORIZA EN ESTE LINK:\n{url}\n",
                success_message="Listo, ya podés cerrar esta pestaña y volver.")
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def publish_short(video_path, title, hook, tags, yt=None, publish_at=None, nicho=None):
    """Sube UN Short a YouTube + comentario con el checkout. Reutilizable desde el
    pipeline para publicar en conjunto con FB+IG. Devuelve el video id.
    publish_at = ISO 8601 UTC con Z (ej '2026-08-01T21:00:00Z') -> lo PROGRAMA
    (privado hasta esa hora, YouTube lo hace público solo, sin PC prendida).

    `nicho` decide el link de compra, los hashtags y el texto del comentario. Sin él se
    usa el de la variable de entorno, que es lo que hacía antes: los scripts sueltos de
    hidroponía siguen funcionando igual."""
    from googleapiclient.http import MediaFileUpload
    yt = yt or get_service()
    status = {"selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    else:
        status["privacyStatus"] = "public"
    body = {"snippet": {"title": title[:100], "description": desc(hook, video_path, nicho),
                        "tags": tags, "categoryId": "26"},
            "status": status}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        _st, resp = req.next_chunk()
    vid = resp.get("id")
    # Un video programado (privado) no se puede comentar hasta que sale público.
    if not publish_at:
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {
                "videoId": vid,
                "topLevelComment": {"snippet": {"textOriginal": comentario(video_path, nicho)}}}}).execute()
        except Exception:
            pass
    return vid


def main():
    from googleapiclient.http import MediaFileUpload
    yt = get_service()
    idx = sys.argv[1] if len(sys.argv) > 1 else None
    vids = [VIDEOS[int(idx)]] if idx is not None else VIDEOS
    for v in vids:
        p = BASE / v["path"]
        if not p.exists():
            print("no existe:", p); continue
        body = {"snippet": {"title": v["title"][:100], "description": desc(v["hook"]),
                            "tags": v["tags"], "categoryId": "26"},
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
        media = MediaFileUpload(str(p), mimetype="video/mp4", resumable=True)
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        print("⏫ subiendo:", v["title"])
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                print(f"   {int(status.progress()*100)}%")
        vid = resp.get("id")
        priv = resp.get("status", {}).get("privacyStatus")
        print(f"   ✅ https://youtube.com/shorts/{vid}   (privacy={priv})")
        # comentario con el link del checkout (siempre)
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {
                "videoId": vid,
                "topLevelComment": {"snippet": {"textOriginal": COMMENT}}}}).execute()
            print("   💬 comentario con el link publicado")
        except Exception as e:
            print(f"   ⚠️ no pude comentar: {str(e)[:80]}")
    print("\nListo. Si quedaron 'private' (proyecto sin auditar), pasalos a público en YouTube Studio.")


if __name__ == "__main__":
    main()
