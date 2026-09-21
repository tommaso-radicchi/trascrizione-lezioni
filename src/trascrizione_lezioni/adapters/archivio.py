"""Adapter reale di archiviazione: scrive il Markdown degli Appunti in una
cartella per Materia sul Mac Mini (vedi CONTEXT.md -> Appunti, issue #6)."""

from __future__ import annotations

from pathlib import Path

from ..dominio import Registrazione


class ArchivioFile:
    def __init__(self, cartella_radice: Path) -> None:
        self._cartella_radice = cartella_radice

    def salva(self, registrazione: Registrazione, appunti_markdown: str) -> str:
        lezione = registrazione.lezione
        cartella_materia = self._cartella_radice / lezione.materia
        cartella_materia.mkdir(parents=True, exist_ok=True)

        id_breve = registrazione.id.split("-")[0]
        percorso = cartella_materia / f"{lezione.data.isoformat()}-{id_breve}.md"
        percorso.write_text(appunti_markdown, encoding="utf-8")
        return str(percorso)
