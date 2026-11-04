"""
Publicación de Reels en Instagram (Content Publishing API).

IG NO acepta el binario directo: requiere el video en una URL pública que
Instagram descarga. Flujo:
  1. Subir el mp4 a un host público (catbox.moe) -> URL directa.
  2. Crear "container": POST /{ig_user_id}/media  (media_type=REELS, video_url, caption)
  3. Esperar status_code=FINISHED (IG procesa el video).
  4. Publicar: POST /{ig_user_id}/media_publish (creation_id).

IG no tiene borradores por API: media_publish sale EN VIVO.
Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import requests

from src.logging_setup import get_logger

log = get_logger()

_WRANGLER = shutil.which("wrangler") or "wrangler"


def _graph(ver: str) -> str:
    return f"https://graph.facebook.com/{ver}"


def get_ig_user_id(page_id: str, token: str, ver: str = "v21.0") -> str | None:
    r = requests.get(f"{_graph(ver)}/{page_id}",
                     params={"fields": "instagram_business_account,connected_instagram_account",
                             "access_token": token}, timeout=30)
    d = r.json()
    iba = d.get("instagram_business_account") or d.get("connected_instagram_account")
    return iba["id"] if iba else None


def upload_r2(path: Path, bucket: str, public_base: str) -> tuple[str, str]:
    """Sube el video a Cloudflare R2 (vía wrangler) y devuelve (url_pública, key)."""
    if not bucket or not public_base:
        raise RuntimeError("Falta R2_BUCKET / R2_PUBLIC_BASE en credenciales para publicar en Instagram.")
    # Key única por reel: todos los videos se llaman publicar.mp4, así que sin el
    # nombre de la carpeta (id del reel) dos publicaciones seguidas colisionan en R2.
    key = f"reels/{path.parent.name}_{path.name}"
    log.info("Subiendo video a R2 (%s/%s)…", bucket, key)
    cmd = (f'"{_WRANGLER}" r2 object put "{bucket}/{key}" '
           f'--file "{path}" --content-type video/mp4 --remote')
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"R2 upload falló: {proc.stderr[-400:] or proc.stdout[-400:]}")
    url = f"{public_base.rstrip('/')}/{key}"
    log.info("Video público en %s", url)
    return url, key


def delete_r2(bucket: str, key: str) -> None:
    try:
        subprocess.run(f'"{_WRANGLER}" r2 object delete "{bucket}/{key}" --remote',
                       shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    except Exception:
        pass


def publish_reel_ig(video_path: Path, caption: str, ig_user_id: str, token: str,
                    r2_bucket: str, r2_public_base: str, ver: str = "v21.0",
                    poll_secs: int = 6, timeout_secs: int = 900) -> str:
    public_url, key = upload_r2(video_path, r2_bucket, r2_public_base)
    # OJO: el borrado de R2 va SOLO si la publicación salió bien. Antes estaba en un
    # 'finally' y borraba el video aunque IG fallara: el reintento se encontraba con un
    # 404 y quedaba imposible de recuperar sin volver a subir todo.
    media_id = _create_and_publish(video_path, caption, ig_user_id, token, ver,
                                   public_url, poll_secs, timeout_secs)
    delete_r2(r2_bucket, key)  # IG ya tiene su copia; recién ahora se limpia R2
    return media_id


# Cuando Meta limita el polling, se espera este rato a ciegas antes de publicar.
ESPERA_CIEGA = 90


def _create_and_publish(video_path, caption, ig_user_id, token, ver, public_url,
                        poll_secs, timeout_secs) -> str:
    # 1. Crear container
    log.info("Instagram: creando container de reel…")
    r = requests.post(f"{_graph(ver)}/{ig_user_id}/media", data={
        "media_type": "REELS", "video_url": public_url,
        "caption": caption, "access_token": token,
    }, timeout=60)
    _raise(r, "crear container")
    creation_id = r.json()["id"]

    # 2. Esperar a que IG procese el video
    waited = 0
    while True:
        st = requests.get(f"{_graph(ver)}/{creation_id}",
                          params={"fields": "status_code,status", "access_token": token},
                          timeout=30).json()
        code = st.get("status_code")
        # Si Meta devuelve un ERROR de API (típico: "(#4) Application request limit
        # reached"), la respuesta NO trae status_code: sin esto el bucle lo leía como
        # "todavía procesando" y quemaba el timeout entero ocultando el motivo real.
        if st.get("error"):
            err = st["error"]
            if err.get("code") == 4 or "request limit" in str(err.get("message", "")).lower():
                # Meta limita CONSULTAR el estado, pero el video se SIGUE procesando y
                # se puede publicar igual (comprobado en el caso real). En vez de abortar:
                # esperamos a ciegas y salimos del bucle para publicar.
                log.warning("Meta limita el polling (error #4) -> espero %ds a ciegas y "
                            "publico igual: el video se procesa aunque no podamos consultar.",
                            ESPERA_CIEGA)
                time.sleep(ESPERA_CIEGA)
                break
            raise RuntimeError(f"Instagram/Meta devolvió un error: {err}")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"Instagram falló al procesar el video: {st.get('status')}")
        if waited >= timeout_secs:
            raise TimeoutError("Instagram tardó demasiado en procesar el reel.")
        time.sleep(poll_secs)
        waited += poll_secs
        log.info("Instagram procesando… (%ds)", waited)

    # 3. Publicar (EN VIVO)
    log.info("Instagram: publicando reel…")
    pub = requests.post(f"{_graph(ver)}/{ig_user_id}/media_publish", data={
        "creation_id": creation_id, "access_token": token,
    }, timeout=60)
    _raise(pub, "media_publish")
    media_id = pub.json()["id"]
    log.info("Instagram: reel publicado. media_id=%s", media_id)
    return media_id


def create_container_only(video_path: Path, caption: str, ig_user_id: str, token: str,
                          r2_bucket: str, r2_public_base: str, ver: str = "v21.0") -> dict:
    """Solo crea el container y espera FINISHED, SIN publicar. Para validar."""
    public_url, _key = upload_r2(video_path, r2_bucket, r2_public_base)
    r = requests.post(f"{_graph(ver)}/{ig_user_id}/media", data={
        "media_type": "REELS", "video_url": public_url,
        "caption": caption, "access_token": token,
    }, timeout=60)
    _raise(r, "crear container")
    creation_id = r.json()["id"]
    waited = 0
    while waited < 180:
        st = requests.get(f"{_graph(ver)}/{creation_id}",
                          params={"fields": "status_code,status", "access_token": token},
                          timeout=30).json()
        if st.get("status_code") == "FINISHED":
            return {"creation_id": creation_id, "public_url": public_url, "status": "FINISHED"}
        if st.get("status_code") == "ERROR":
            return {"creation_id": creation_id, "public_url": public_url, "status": st}
        time.sleep(6); waited += 6
    return {"creation_id": creation_id, "public_url": public_url, "status": "TIMEOUT"}


def _raise(resp: requests.Response, step: str) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(f"Instagram falló en '{step}' [{resp.status_code}]: {resp.text[:300]}")
    body = resp.json()
    if isinstance(body, dict) and body.get("error"):
        raise RuntimeError(f"Instagram error en '{step}': {body['error']}")
