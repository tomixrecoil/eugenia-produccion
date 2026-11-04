"""
Cliente Gemini único y compartido.

El SDK google-genai comparte un cliente httpx interno; crear varios `genai.Client`
y dejar que el recolector de basura cierre alguno rompe a los demás con
"Cannot send a request, as the client has been closed.". Con un único cliente
cacheado por api_key evitamos ese cierre.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from src.logging_setup import get_logger

log = get_logger()

# ---------------------------------------------------------------------------
# ACTIVIDAD RECIENTE — a pedido de Tomix (11/09): "quiero ver qué está pensando
# Gemini" — qué modelo, qué se le mandó y qué contestó, en vivo. generate() es el
# único cuello de botella real por el que pasan casi todas las llamadas de
# "pensamiento" (análisis de video, guion, copy, doblaje, ventas) — instrumentando
# acá se captura todo eso de una sola vez, sin tocar cada uno de los ~10 call sites.
# Quedan afuera las llamadas de voz/TTS que hacen generate_content directo (voz_charon,
# voz_gemini, el chequeo de audio de producir_stock): son ruido, no "pensamiento".
_ACTIVIDAD: deque = deque(maxlen=200)


def _preview(contents, tope: int = 900) -> str:
    """Texto legible de lo que se mandó. `contents` puede traer un archivo adjunto
    (video/imagen) mezclado con el prompt de texto — el archivo no se puede mostrar,
    así que se anota nada más."""
    partes = contents if isinstance(contents, list) else [contents]
    out = []
    for p in partes:
        if isinstance(p, str):
            out.append(p)
        else:
            nombre = type(p).__name__
            out.append(f"[adjunto: {nombre}]")
    texto = "\n".join(out)
    return texto if len(texto) <= tope else texto[:tope] + "…"


def actividad_reciente(n: int = 50) -> list[dict]:
    """Las últimas N llamadas reales a Gemini, más nuevas primero."""
    return list(_ACTIVIDAD)[-n:][::-1]


# ---------------------------------------------------------------------------
# PARÁMETROS EDITABLES A MANO — a pedido de Tomix (11/09): antes la temperatura
# estaba escrita fija en cada archivo que llamaba a generate() (0.85 en
# copywrite.py, sin setear = default de la API en los demás). Se lee de
# parametros_ia.json (raíz del proyecto, lo edita la pestaña Modelos vía
# webapp.py) para que cambiarla no requiera tocar código. Sin el archivo, o con
# un valor inválido, sigue el comportamiento de siempre (temperatura por
# defecto de la API, ~1.0).
_PARAMS_PATH = Path(__file__).resolve().parent.parent / "parametros_ia.json"


def parametros_gemini() -> dict:
    try:
        data = json.loads(_PARAMS_PATH.read_text(encoding="utf-8"))
        return data.get("gemini") or {}
    except Exception:  # noqa: BLE001
        return {}


@lru_cache(maxsize=64)
def get_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def keys() -> list[str]:
    """Todas las API keys de Gemini configuradas, en orden de prioridad. Sin tope
    fijo: escanea GEMINI_API_KEY, _2, _3... hasta encontrar 3 huecos seguidos (por
    si algún día se borra una del medio a mano) — así agregar una cuenta nueva es
    solo cargar la siguiente variable en .env, nunca tocar este archivo (a pedido
    de Tomix, 04/09: el límite de 5 era arbitrario)."""
    out = []
    huecos = 0
    i = 1
    while huecos < 3:
        name = "GEMINI_API_KEY" if i == 1 else f"GEMINI_API_KEY_{i}"
        v = (os.getenv(name) or "").strip()
        if v:
            out.append(v)
            huecos = 0
        else:
            huecos += 1
        i += 1
    return out


def _rotatable(e: Exception) -> bool:
    """True si conviene pasar a la siguiente key: cuota diaria agotada o key inválida/sin permiso."""
    code = getattr(e, "code", None)
    msg = str(e).lower()
    if code == 429 and ("perday" in msg.replace(" ", "") or "quota" in msg):
        return True
    return code in (400, 401, 403)


def run(call, key_list: list[str] | None = None):
    """Ejecuta call(client) rotando de API key si la actual agota su cuota diaria o es inválida.
    `call` recibe un genai.Client (puede subir archivos, generar, etc.) y devuelve lo que sea."""
    ks = key_list or keys()
    if not ks:
        raise RuntimeError("No hay GEMINI_API_KEY configurada.")
    last = None
    for i, k in enumerate(ks):
        try:
            return call(get_client(k))
        except Exception as e:  # noqa: BLE001
            last = e
            if _rotatable(e):
                if i < len(ks) - 1:
                    log.warning("Gemini key %d/%d agotada o inválida (%s) -> roto a la siguiente.",
                                i + 1, len(ks), getattr(e, "code", type(e).__name__))
                    continue
                # Última key también agotada/ inválida -> avisar por email.
                from src import notify
                notify.alert(
                    "Gemini sin cuota en TODAS las keys",
                    f"Se agotó la cuota diaria (o son inválidas) de las {len(ks)} API keys de "
                    "Gemini. El pipeline no puede analizar/generar hasta el reset diario o hasta "
                    "agregar otra key en .env (GEMINI_API_KEY_6).",
                    dedup_key="gemini_exhausted")
            raise
    raise last


def generate(client: genai.Client, model: str, contents, retries: int = 5,
             system: str | None = None):
    """generate_content con reintentos ante errores transitorios (503/UNAVAILABLE, 429).
    Cada intento queda registrado en _ACTIVIDAD (ver actividad_reciente()).
    La temperatura sale de parametros_ia.json (editable desde la pestaña Modelos);
    sin valor cargado, se manda igual que siempre (sin `config`, default de la API)."""
    prompt_txt = _preview(contents)
    t0 = time.monotonic()
    temp = parametros_gemini().get("temperatura")
    # `system`: instrucción de sistema opcional (ej. la referencia de reels ganadores,
    # ver src/referencia.py). Sin ella, el pedido sale igual que siempre.
    cfg = {}
    if temp is not None:
        cfg["temperature"] = temp
    if system:
        cfg["system_instruction"] = system
    gen_config = genai_types.GenerateContentConfig(**cfg) if cfg else None
    for attempt in range(retries):
        entrada = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
                   "modelo": model, "intento": attempt + 1, "prompt": prompt_txt}
        try:
            r = client.models.generate_content(model=model, contents=contents, config=gen_config)
            entrada["ms"] = int((time.monotonic() - t0) * 1000)
            entrada["ok"] = True
            entrada["respuesta"] = _preview(getattr(r, "text", "") or "")
            _ACTIVIDAD.append(entrada)
            return r
        except genai_errors.ServerError as e:  # 5xx (503 high demand, etc.)
            entrada["ms"] = int((time.monotonic() - t0) * 1000)
            entrada["ok"] = False
            entrada["error"] = str(e)[:200]
            _ACTIVIDAD.append(entrada)
            if attempt == retries - 1:
                raise
            wait = 8 * (attempt + 1)
            log.warning("Gemini no disponible (%s). Reintento en %ds (%d/%d)…",
                        getattr(e, "code", "5xx"), wait, attempt + 1, retries)
            time.sleep(wait)
        except genai_errors.ClientError as e:
            entrada["ms"] = int((time.monotonic() - t0) * 1000)
            entrada["ok"] = False
            entrada["error"] = str(e)[:200]
            _ACTIVIDAD.append(entrada)
            if getattr(e, "code", None) == 429:
                msg = str(e)
                # Cuota DIARIA agotada -> reintentar no sirve (no se libera por horas).
                if "PerDay" in msg or "per day" in msg.lower():
                    raise
                if attempt < retries - 1:
                    wait = 15 * (attempt + 1)
                    log.warning("Gemini rate limit por minuto (429). Reintento en %ds…", wait)
                    time.sleep(wait)
                    continue
            raise
