"""
Interruptores de "producción" y "encolado" por nicho, a pedido de Tomix (14/09):
que él pueda prender/apagar cada uno desde el panel, sin pedírmelo, y que por
default un nicho que ya viene andando (bonsái) no se apague por sorpresa.

Vive en R2 (state/toggles.json), no localmente: así lo puede leer tanto la PC
(producir_stock.py, encolar_stock.py) como el Worker en la nube (el cron de
encolado no depende de que la PC esté prendida).

Si el archivo no existe, o le falta un nicho, el default es ACTIVO (true) para
los dos interruptores — un nicho nuevo, o si algo falla al leer, sigue
funcionando como hasta ahora en vez de apagarse solo en silencio.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "cloudflare-worker"
KEY = "marketing-reels/state/toggles.json"

# fb / ig / yt (02/11/2026): en qué plataformas publica el nicho. Antes vivían en
# niches/*.yaml (publish_*), escondidos, y el Worker no los miraba: publicaba siempre en
# FB e IG. Ahora el Worker (publicarDeStock) y la subida a YouTube los leen de acá.
CLAVES = ("produccion", "encolado", "fb", "ig", "yt")


def leer() -> dict:
    import r2io
    if r2io.en_nube():
        d = r2io.get_json(KEY)
        return d if isinstance(d, dict) else {}
    p = subprocess.run(
        ["npx", "wrangler", "r2", "object", "get", KEY, "--remote", "--pipe"],
        cwd=WORKER, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60, shell=True)
    if p.returncode == 0 and p.stdout.strip():
        try:
            d = json.loads(p.stdout)
            return d if isinstance(d, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def guardar(d: dict) -> bool:
    tmp = Path(tempfile.gettempdir()) / "toggles.json"
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    p = subprocess.run(
        ["npx", "wrangler", "r2", "object", "put", KEY, "--file", str(tmp),
         "--content-type", "application/json", "--remote"],
        cwd=WORKER, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60, shell=True)
    return p.returncode == 0


def activo(nicho: str, clave: str) -> bool:
    """True si ese nicho tiene ESE interruptor prendido (o no está configurado
    -> default activo, para no romper nichos que nunca tocaron esto)."""
    d = leer()
    return bool((d.get(nicho) or {}).get(clave, True))


def set_toggle(nicho: str, clave: str, valor: bool) -> bool:
    if clave not in CLAVES:
        raise ValueError(f"clave inválida: {clave!r} (válidas: {CLAVES})")
    d = leer()
    d.setdefault(nicho, {})[clave] = bool(valor)
    return guardar(d)


# Horarios de publicación por nicho (horas ART, 0-23), también en state/toggles.json para
# que la PC, la nube y el Worker lean el mismo valor y se cambien desde el panel, no en el
# código (Tomix, 01/11). Si falta o es inválido, cada uno usa su default (6 y 18).
HORAS_DEFAULT = (6, 18)


def horas_validas(valor) -> tuple[int, ...] | None:
    try:
        hs = tuple(sorted({int(h) for h in valor}))
    except (TypeError, ValueError):
        return None
    return hs if hs and all(0 <= h <= 23 for h in hs) else None


def horas(nicho: str, d: dict | None = None) -> tuple[int, ...]:
    d = leer() if d is None else d
    return horas_validas((d.get(nicho) or {}).get("horas")) or HORAS_DEFAULT


def set_horas(nicho: str, valor) -> bool:
    hs = horas_validas(valor)
    if not hs:
        raise ValueError(f"horarios inválidos: {valor!r}")
    d = leer()
    d.setdefault(nicho, {})["horas"] = list(hs)
    return guardar(d)
