"""Vocabolario di dominio: vedi CONTEXT.md alla radice del repo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum, auto


class Stato(Enum):
    """Il ciclo di vita di una Registrazione, definito in CONTEXT.md."""

    RICEVUTA = auto()
    TRASCRITTA = auto()
    ELABORATA = auto()
    ARCHIVIATA = auto()
    NOTIFICATA = auto()
    ERRORE = auto()


@dataclass
class Lezione:
    """Materia + giorno: raccoglie tutte le Registrazioni della stessa sessione."""

    id: str
    materia: str
    data: date
    chat_id: str


@dataclass
class Registrazione:
    id: str
    lezione: Lezione
    percorso_audio: str
    stato: Stato = Stato.RICEVUTA
    trascrizione: str | None = None
    appunti_markdown: str | None = None
    percorso_appunti: str | None = None
    tentativi: int = 0
