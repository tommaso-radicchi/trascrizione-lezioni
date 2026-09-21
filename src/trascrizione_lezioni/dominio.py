"""Vocabolario di dominio: vedi CONTEXT.md alla radice del repo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum, auto


class Stato(Enum):
    """Il ciclo di vita di una Registrazione, definito in CONTEXT.md."""

    RICEVUTA = auto()
    TRASCRITTA = auto()
    SEGMENTATA = auto()
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


@dataclass(frozen=True)
class PropostaCapitolo:
    """Cosa restituisce il LLM per ogni Capitolo: titolo e prime parole del blocco."""

    titolo: str
    frase_inizio: str


@dataclass(frozen=True)
class CapitoloTagliato:
    """Un Capitolo appena tagliato: il testo è un ritaglio esatto della Trascrizione."""

    titolo: str
    testo: str


@dataclass(frozen=True)
class Capitolo:
    registrazione_id: str
    posizione: int
    titolo: str
    testo: str
