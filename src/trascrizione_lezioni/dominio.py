"""Vocabolario di dominio: vedi CONTEXT.md alla radice del repo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum, auto
from typing import Any


class Stato(Enum):
    """Il ciclo di vita di una Registrazione, definito in CONTEXT.md."""

    RICEVUTA = auto()
    TRASCRITTA = auto()
    SEGMENTATA = auto()
    ELABORATA = auto()
    ARCHIVIATA = auto()
    NOTIFICATA = auto()
    ERRORE = auto()


class StatoComprensione(Enum):
    """Lo stato di un Capitolo, scelto a mano dal fratello (CONTEXT.md -> Stato di comprensione)."""

    DA_STUDIARE = "da_studiare"
    IN_CORSO = "in_corso"
    COMPRESO = "compreso"
    DA_RIPASSARE = "da_ripassare"


@dataclass
class Lezione:
    """Materia + giorno: raccoglie tutte le Registrazioni della stessa sessione."""

    id: str
    materia: str
    data: date
    chat_id: str
    # Ricalcolato dai riassunti dei Capitoli a ogni nuovo Capitolo (vedi CONTEXT.md -> Appunti).
    quadro_generale: str | None = None


@dataclass
class Registrazione:
    id: str
    lezione: Lezione
    percorso_audio: str
    stato: Stato = Stato.RICEVUTA
    trascrizione: str | None = None
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
class Termine:
    termine: str
    definizione: str


@dataclass(frozen=True)
class Domanda:
    domanda: str
    risposta: str


@dataclass(frozen=True)
class AppuntiCapitolo:
    """Gli Appunti di un Capitolo, in forma strutturata: il Markdown si ricompone da qui."""

    riassunto: str
    punti_chiave: list[str] = field(default_factory=list)
    termini: list[Termine] = field(default_factory=list)
    da_ripassare: list[str] = field(default_factory=list)
    domande: list[Domanda] = field(default_factory=list)

    def a_dict(self) -> dict[str, Any]:
        return {
            "riassunto": self.riassunto,
            "punti_chiave": list(self.punti_chiave),
            "termini": [{"termine": t.termine, "definizione": t.definizione} for t in self.termini],
            "da_ripassare": list(self.da_ripassare),
            "domande": [{"domanda": d.domanda, "risposta": d.risposta} for d in self.domande],
        }

    @classmethod
    def da_dict(cls, dati: dict[str, Any]) -> AppuntiCapitolo:
        """Solo il riassunto è obbligatorio: le liste mancanti o nulle sono vuote."""
        try:
            return cls(
                riassunto=str(dati["riassunto"]),
                punti_chiave=[str(p) for p in dati.get("punti_chiave") or []],
                termini=[
                    Termine(str(t["termine"]), str(t["definizione"]))
                    for t in dati.get("termini") or []
                ],
                da_ripassare=[str(p) for p in dati.get("da_ripassare") or []],
                domande=[
                    Domanda(str(d["domanda"]), str(d["risposta"]))
                    for d in dati.get("domande") or []
                ],
            )
        except (KeyError, TypeError) as errore:
            raise ValueError(f"Appunti del Capitolo con forma non valida: {errore!r}") from errore


@dataclass(frozen=True)
class Capitolo:
    registrazione_id: str
    posizione: int
    titolo: str
    testo: str
    appunti: AppuntiCapitolo | None = None
