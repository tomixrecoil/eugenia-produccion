#!/usr/bin/env python3
"""Regenera Whapi/_export/Whapi - Documento completo.md juntando todas las notas en orden.
Uso:  python Whapi/codigo/regenerar_export.py"""
import re
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
partes = [f"# Whapi — Documento completo\n\n> Todas las notas del vault en un solo archivo. "
          f"Generado el {date.today():%d/%m/%Y}. Fuente canónica: tomixrecoil/eugenia-carritos/Whapi.\n"]
for p in sorted(VAULT.glob("*.md")):
    t = re.sub(r"^---\n.*?\n---\n", "", p.read_text(encoding="utf-8"), flags=re.S)
    partes.append(f"\n\n---\n\n<!-- {p.name} -->\n{t.strip()}\n")
(VAULT / "_export").mkdir(exist_ok=True)
(VAULT / "_export" / "Whapi - Documento completo.md").write_text("".join(partes), encoding="utf-8")
print("ok", len(partes) - 1, "notas")
