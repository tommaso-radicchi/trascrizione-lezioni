"""Implementazioni finte/in-memory delle 6 porte, per test e per l'harness di sviluppo."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from ..dominio import Lezione, Registrazione, Stato


class ControlloGpuFake:
    def __init__(self, libera: bool = True) -> None:
        self.stato_libera = libera

    def libera(self) -> bool:
        return self.stato_libera


class ClientTrascrizioneFake:
    def __init__(self, comportamento: Callable[[str], str] | None = None) -> None:
        self._comportamento = comportamento or (
            lambda percorso_audio: f"trascrizione di {percorso_audio}"
        )
        self.chiamate: list[str] = []

    def trascrivi(self, percorso_audio: str) -> str:
        self.chiamate.append(percorso_audio)
        return self._comportamento(percorso_audio)


class ClientAppuntiFake:
    def __init__(self, comportamento: Callable[[str, str, date], str] | None = None) -> None:
        self._comportamento = comportamento or (
            lambda trascrizione, materia, data: f"# {materia} ({data})\n\n{trascrizione}"
        )
        self.chiamate: list[tuple[str, str, date]] = []

    def genera_appunti(self, trascrizione: str, materia: str, data: date) -> str:
        self.chiamate.append((trascrizione, materia, data))
        return self._comportamento(trascrizione, materia, data)


class ArchivioFake:
    def __init__(self) -> None:
        self.salvati: dict[str, str] = {}

    def salva(self, registrazione: Registrazione, appunti_markdown: str) -> str:
        percorso = f"archivio/{registrazione.lezione.materia}/{registrazione.id}.md"
        self.salvati[percorso] = appunti_markdown
        return percorso


class RepositoryFake:
    def __init__(self, registrazioni: list[Registrazione] | None = None) -> None:
        self._lezioni: dict[str, Lezione] = {}
        self._registrazioni: dict[str, Registrazione] = {}
        for registrazione in registrazioni or []:
            self.salva_registrazione(registrazione)

    def trova_lezione(self, materia: str, data: date) -> Lezione | None:
        for lezione in self._lezioni.values():
            if lezione.materia == materia and lezione.data == data:
                return lezione
        return None

    def salva_lezione(self, lezione: Lezione) -> None:
        self._lezioni[lezione.id] = lezione

    def salva_registrazione(self, registrazione: Registrazione) -> None:
        self._lezioni[registrazione.lezione.id] = registrazione.lezione
        self._registrazioni[registrazione.id] = registrazione

    def registrazioni_da_processare(self) -> list[Registrazione]:
        return [
            registrazione
            for registrazione in self._registrazioni.values()
            if registrazione.stato not in (Stato.NOTIFICATA, Stato.ERRORE)
        ]

    def lezioni(self) -> list[Lezione]:
        return list(self._lezioni.values())

    def registrazioni(self) -> list[Registrazione]:
        return list(self._registrazioni.values())


class ClientTelegramFake:
    def __init__(self) -> None:
        self.appunti_inviati: list[tuple[Lezione, str]] = []
        self.errori_notificati: list[tuple[Lezione, str]] = []
        self.materie_richieste: list[tuple[str, list[str]]] = []
        self.conferme_inviate: list[str] = []

    def invia_appunti(self, lezione: Lezione, percorso_appunti: str) -> None:
        self.appunti_inviati.append((lezione, percorso_appunti))

    def notifica_errore(self, lezione: Lezione, messaggio: str) -> None:
        self.errori_notificati.append((lezione, messaggio))

    def chiedi_materia(self, chat_id: str, materie: list[str]) -> None:
        self.materie_richieste.append((chat_id, materie))

    def conferma_ricezione(self, chat_id: str) -> None:
        self.conferme_inviate.append(chat_id)
