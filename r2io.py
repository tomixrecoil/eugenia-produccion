#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Leer y escribir en R2 desde la NUBE (GitHub Actions), sin la PC.

En la PC todo va por `npx wrangler` con el login de Tomix. En GitHub no hay ese login,
y una llave del bucket entero vería las conversaciones y los teléfonos de los clientes
que viven en el mismo bucket. Por eso la nube pasa por la "puerta" (Worker
eugenia-puerta-r2): una clave propia que SOLO deja tocar los videos, el stock y los
registros de fuentes.

Si PUERTA_R2_URL no está definida estamos en la PC y nadie llama a esto: los módulos
de siempre siguen usando wrangler.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BUCKET = "marketing-reels"


def en_nube() -> bool:
    return bool((os.getenv("PUERTA_R2_URL") or "").strip())


def _url(key: str) -> str:
    # Los módulos de la PC nombran las claves con el bucket adelante (es lo que pide
    # wrangler); la puerta trabaja dentro del bucket.
    if key.startswith(BUCKET + "/"):
        key = key[len(BUCKET) + 1:]
    base = os.environ["PUERTA_R2_URL"].strip().rstrip("/")
    return f"{base}/o/{urllib.parse.quote(key)}"


def _pedido(key: str, metodo: str, datos=None, ctype: str = "", largo: int | None = None):
    req = urllib.request.Request(_url(key), data=datos, method=metodo)
    req.add_header("x-clave", os.environ["PUERTA_R2_KEY"].strip())
    # Sin esto Cloudflare corta con 403 (error 1010): bloquea el "Python-urllib" por defecto.
    req.add_header("user-agent", "eugenia-produccion/1.0")
    if ctype:
        req.add_header("content-type", ctype)
    if largo is not None:
        req.add_header("content-length", str(largo))
    return urllib.request.urlopen(req, timeout=600)


def get_bytes(key: str) -> bytes | None:
    """El contenido, o None si no existe o la puerta no responde."""
    try:
        with _pedido(key, "GET") as r:
            return r.read()
    except (urllib.error.URLError, OSError):
        return None


def get_json(key: str):
    b = get_bytes(key)
    if not b:
        return None
    try:
        return json.loads(b.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def bajar(key: str, destino: Path) -> bool:
    """Baja un archivo grande a disco sin cargarlo entero en memoria."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _pedido(key, "GET") as r, open(destino, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        return True
    except (urllib.error.URLError, OSError):
        destino.unlink(missing_ok=True)
        return False


def put_file(local: Path, key: str, ctype: str) -> bool:
    local = Path(local)
    try:
        with open(local, "rb") as f, _pedido(key, "PUT", f, ctype, local.stat().st_size) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError):
        return False


def put_json(key: str, datos) -> bool:
    b = json.dumps(datos, ensure_ascii=False, indent=1).encode("utf-8")
    try:
        with _pedido(key, "PUT", b, "application/json", len(b)) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError):
        return False


def delete(key: str) -> bool:
    try:
        with _pedido(key, "DELETE") as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError):
        return False


def cargar_credenciales() -> int:
    """Las claves de voz e IA desde la bóveda chica (panel/boveda_produccion.json), así un
    cambio hecho desde el panel web llega a la producción sin tocar los secrets de GitHub.
    Pisan a las variables de entorno; si la bóveda no está o falla, siguen los secrets.
    Devuelve cuántas cargó. Ver boveda.py y analisis/REDISENO_0211.md."""
    import base64
    llave = (os.getenv("BOVEDA_PRODUCCION_KEY") or "").strip()
    if not (en_nube() and llave):
        return 0
    caja = get_json("panel/boveda_produccion.json")
    if not caja:
        return 0
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        plano = AESGCM(base64.b64decode(llave)).decrypt(
            base64.b64decode(caja["iv"]), base64.b64decode(caja["ct"]), None)
        datos = json.loads(plano.decode("utf-8"))
    except Exception:  # noqa: BLE001 — una bóveda rota no puede frenar la producción
        return 0
    for k, v in datos.items():
        if str(v or "").strip():
            os.environ[k] = str(v)
    return len(datos)


def bajar_nichos(carpeta: Path) -> list[str]:
    """Los ajustes de cada nicho (voz, mockup, logo, subtítulos...) tal como se guardaron
    en el panel: la PC los sube a state/nichos/<nicho>.yaml al guardar (config.py,
    subir_nicho_nube). Pisan a la copia que trajo exportar_produccion.py; si falta o no
    es un yaml válido, queda la copia. Antes los ajustes eran decoración para la nube
    (Tomix, 02/11/2026; analisis/AJUSTES_DECORACION.md). Devuelve los que bajó."""
    import yaml
    if not en_nube():
        return []
    bajados = []
    for f in sorted(Path(carpeta).glob("*.yaml")):
        b = get_bytes(f"state/nichos/{f.name}")
        if not b:
            continue
        try:
            datos = yaml.safe_load(b.decode("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(datos, dict) and datos.get("cta_link") is not None:
            f.write_bytes(b)
            bajados.append(f.stem)
    return bajados
