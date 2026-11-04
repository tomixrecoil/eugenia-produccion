"""
Publicación del reel en una Facebook Page vía Meta Graph API (subida resumable).

Flujo oficial en 3 fases (endpoint /{page_id}/video_reels):
  1. start   -> devuelve video_id + upload_url
  2. upload  -> POST binario a rupload.facebook.com con header OAuth
  3. finish  -> publica (video_state=PUBLISHED) con la descripción/copy

Docs: https://developers.facebook.com/docs/video-api/guides/reels-publishing
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from src.logging_setup import get_logger

log = get_logger()

# Botón "Contactar por WhatsApp" en TODOS los reels de la página. Va como DEFAULT acá
# (y no en cada script que publica) para que ninguna vía de publicación se lo saltee.
# Para publicar sin botón hay que pasar call_to_action=None explícitamente.
WHATSAPP_CTA = json.dumps({"type": "WHATSAPP_MESSAGE",
                           "value": {"app_destination": "WHATSAPP"}})


class PublishError(RuntimeError):
    pass


def _graph(version: str) -> str:
    return f"https://graph.facebook.com/{version}"


def publish_reel(
    video_path: Path,
    description: str,
    page_id: str,
    page_token: str,
    graph_version: str = "v21.0",
    video_state: str = "PUBLISHED",
    scheduled_publish_time: int | None = None,
    call_to_action: str | None = WHATSAPP_CTA,
) -> str:
    if not page_token:
        raise PublishError("Falta META_PAGE_ACCESS_TOKEN.")

    file_size = os.path.getsize(video_path)
    base = f"{_graph(graph_version)}/{page_id}/video_reels"

    # --- Fase 1: start ---
    log.info("Meta: iniciando subida de reel…")
    r = requests.post(base, data={"upload_phase": "start", "access_token": page_token})
    _raise_for_graph(r, "start")
    start = r.json()
    video_id = start["video_id"]
    upload_url = start["upload_url"]

    # --- Fase 2: subir binario ---
    log.info("Meta: subiendo binario (%.1f MB)…", file_size / 1e6)
    with open(video_path, "rb") as f:
        up = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {page_token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            data=f.read(),
        )
    _raise_for_graph(up, "upload")

    # --- Fase 3: finish + publicar ---
    log.info("Meta: finalizando (state=%s%s)…", video_state,
             f", programado ts={scheduled_publish_time}" if scheduled_publish_time else "")
    finish_data = {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": video_state,
        "description": description,
        "access_token": page_token,
    }
    if video_state == "SCHEDULED" and scheduled_publish_time:
        finish_data["scheduled_publish_time"] = str(scheduled_publish_time)
    # Botón "Contactar por WhatsApp" (call_to_action). La API lo acepta pero NO expone
    # el campo para releer: solo se verifica mirando el reel en Facebook.
    if call_to_action:
        finish_data["call_to_action"] = call_to_action
    fin = requests.post(base, data=finish_data)
    _raise_for_graph(fin, "finish")

    log.info("Meta: reel publicado. video_id=%s", video_id)
    return video_id


def _raise_for_graph(resp: requests.Response, phase: str) -> None:
    if resp.status_code >= 400:
        raise PublishError(f"Meta Graph API falló en fase '{phase}' "
                           f"[{resp.status_code}]: {resp.text}")
    try:
        body = resp.json()
    except ValueError:
        return
    if isinstance(body, dict) and body.get("error"):
        raise PublishError(f"Meta Graph API error en fase '{phase}': {body['error']}")
    if isinstance(body, dict) and body.get("success") is False:
        raise PublishError(f"Meta reportó fallo en fase '{phase}': {body}")
