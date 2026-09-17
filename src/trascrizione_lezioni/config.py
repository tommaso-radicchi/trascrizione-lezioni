"""Caricamento della configurazione delle Materie correnti (CONTEXT.md -> Materia)."""

from __future__ import annotations

from pathlib import Path

import yaml


def carica_materie_correnti(percorso: Path) -> list[str]:
    dati = yaml.safe_load(percorso.read_text(encoding="utf-8"))
    if not isinstance(dati, list):
        raise ValueError(f"{percorso} deve contenere una lista di materie, non {type(dati)}")
    return [str(materia) for materia in dati]
