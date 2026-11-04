"""Persistencia simple de videos ya procesados (para no repetir/publicar dos veces)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"


def _state_file(niche: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{niche}_processed.json"


def load_processed(niche: str) -> dict:
    f = _state_file(niche)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def processed_ids(niche: str) -> set[str]:
    return set(load_processed(niche).keys())


def mark_processed(niche: str, video_id: str, record: dict) -> None:
    data = load_processed(niche)
    data[video_id] = record
    _state_file(niche).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
