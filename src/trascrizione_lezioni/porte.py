"""Le 6 porte iniettabili dell'Orchestratore: i confini verso il mondo esterno."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from .dominio import Lezione


class ControlloGpu(Protocol):
    def libera(self) -> bool: ...


class ClientTrascrizione(Protocol):
    def trascrivi(self, percorso_audio: str) -> str: ...


class ClientAppunti(Protocol):
    def genera_appunti(self, trascrizione: str, materia: str, data: date) -> str: ...


class Archivio(Protocol):
    def salva(self, lezione: Lezione, appunti_markdown: str) -> str: ...


class Repository(Protocol):
    def salva(self, lezione: Lezione) -> None: ...
    def da_processare(self) -> list[Lezione]: ...


class ClientTelegram(Protocol):
    def invia_appunti(self, lezione: Lezione, percorso_appunti: str) -> None: ...
    def notifica_errore(self, lezione: Lezione, messaggio: str) -> None: ...
    def chiedi_materia(self, chat_id: str, materie: list[str]) -> None: ...
    def conferma_ricezione(self, chat_id: str) -> None: ...
