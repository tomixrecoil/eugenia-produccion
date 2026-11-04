"""
Análisis de video frame-by-frame con Gemini (la única IA del pipeline que "ve" el video).

Usa el SDK google-genai:
  - sube el mp4 con la File API,
  - espera a que Gemini lo procese,
  - genera la transcripción + descripción según el prompt del nicho.
"""
from __future__ import annotations

import time
from pathlib import Path

from src import gemini_client
from src.gemini_client import get_client
from src.logging_setup import get_logger

log = get_logger()


def analyze_video(
    video_path: Path,
    prompt: str,
    api_key: str,
    model: str,
    poll_secs: int = 5,
    timeout_secs: int = 600,
) -> str:
    def call(client):
        log.info("Subiendo video a Gemini File API…")
        myfile = client.files.upload(file=str(video_path))

        # Esperar a que termine el procesamiento del archivo.
        waited = 0
        while myfile.state.name == "PROCESSING":
            if waited >= timeout_secs:
                raise TimeoutError("Gemini tardó demasiado en procesar el video.")
            time.sleep(poll_secs)
            waited += poll_secs
            myfile = client.files.get(name=myfile.name)

        if myfile.state.name == "FAILED":
            raise RuntimeError("Gemini falló al procesar el video.")

        log.info("Analizando con %s…", model)
        response = gemini_client.generate(client, model, [myfile, prompt])

        # Limpieza: borrar el archivo subido para no acumular en la cuenta.
        try:
            client.files.delete(name=myfile.name)
        except Exception:
            pass
        return (response.text or "").strip()

    # Rota de key (key1 -> key2 -> ...) si la actual agota su cuota diaria.
    text = gemini_client.run(call)
    if not text:
        raise RuntimeError("Gemini devolvió una respuesta vacía.")
    log.info("Descripción generada (%d caracteres).", len(text))
    return text
