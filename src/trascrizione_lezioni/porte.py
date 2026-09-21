"""Le 7 porte iniettabili dell'Orchestratore: i confini verso il mondo esterno."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from .dominio import (
    AppuntiCapitolo,
    Capitolo,
    CapitoloTagliato,
    Lezione,
    PropostaCapitolo,
    Registrazione,
)


class ControlloGpu(Protocol):
    def libera(self) -> bool: ...


class ClientTrascrizione(Protocol):
    def trascrivi(self, percorso_audio: str) -> str: ...


class ClientSegmentazione(Protocol):
    def proponi_capitoli(self, trascrizione: str) -> list[PropostaCapitolo]:
        """Solleva SegmentazioneNonValida se la risposta del modello non è utilizzabile."""
        ...


class ClientAppunti(Protocol):
    def genera_appunti_capitolo(self, titolo: str, testo: str, materia: str) -> AppuntiCapitolo: ...
    def genera_quadro_generale(
        self, materia: str, data: date, riassunti: list[tuple[str, str]]
    ) -> str:
        """Il quadro generale della Lezione, dai (titolo, riassunto) dei suoi Capitoli."""
        ...


class Archivio(Protocol):
    def salva(self, lezione: Lezione, appunti_markdown: str) -> str:
        """Scrive il Markdown della Lezione (un file per Lezione) e ne restituisce il percorso."""
        ...


class Repository(Protocol):
    def trova_lezione(self, materia: str, data: date) -> Lezione | None: ...
    def salva_lezione(self, lezione: Lezione) -> None: ...
    def salva_registrazione(self, registrazione: Registrazione) -> None: ...
    def sostituisci_capitoli(
        self, registrazione: Registrazione, capitoli: list[CapitoloTagliato]
    ) -> None:
        """Salva i Capitoli della Registrazione, sostituendo quelli di un tentativo precedente."""
        ...
    def salva_appunti(self, capitolo: Capitolo, appunti: AppuntiCapitolo) -> None: ...
    def salva_quadro_generale(self, lezione: Lezione, quadro_generale: str) -> None: ...
    def capitoli_della_lezione(self, lezione: Lezione) -> list[Capitolo]:
        """Nell'ordine di arrivo delle Registrazioni, poi di posizione nella Registrazione."""
        ...
    def registrazioni_da_processare(self) -> list[Registrazione]:
        """Le Registrazioni non ancora notificate né in errore, in ordine di arrivo."""
        ...


class ClientTelegram(Protocol):
    def notifica_appunti(
        self, lezione: Lezione, titoli_nuovi: list[str], link: str | None
    ) -> None:
        """Avvisa che sono pronti degli Appunti nuovi, con i titoli dei Capitoli aggiunti e,
        se il sito è configurato, il link al primo."""
        ...
    def notifica_errore(self, lezione: Lezione, messaggio: str) -> None: ...
    def chiedi_materia(self, chat_id: str, materie: list[str]) -> None: ...
    def conferma_ricezione(self, chat_id: str) -> None: ...
