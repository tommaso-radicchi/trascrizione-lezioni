"""Implementazioni finte/in-memory delle 6 porte, per test e per l'harness di sviluppo."""

from __future__ import annotations

from collections.abc import Callable

from ..dominio import Lezione, Stato


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
    def __init__(self, comportamento: Callable[[str, str], str] | None = None) -> None:
        self._comportamento = comportamento or (
            lambda trascrizione, materia: f"# Appunti di {materia}\n\n{trascrizione}"
        )
        self.chiamate: list[tuple[str, str]] = []

    def genera_appunti(self, trascrizione: str, materia: str) -> str:
        self.chiamate.append((trascrizione, materia))
        return self._comportamento(trascrizione, materia)


class ArchivioFake:
    def __init__(self) -> None:
        self.salvati: dict[str, str] = {}

    def salva(self, lezione: Lezione, appunti_markdown: str) -> str:
        percorso = f"archivio/{lezione.materia}/{lezione.id}.md"
        self.salvati[percorso] = appunti_markdown
        return percorso


class RepositoryFake:
    def __init__(self, lezioni: list[Lezione] | None = None) -> None:
        self._lezioni: dict[str, Lezione] = {l.id: l for l in (lezioni or [])}

    def salva(self, lezione: Lezione) -> None:
        self._lezioni[lezione.id] = lezione

    def da_processare(self) -> list[Lezione]:
        return [
            lezione
            for lezione in self._lezioni.values()
            if lezione.stato not in (Stato.NOTIFICATA, Stato.ERRORE)
        ]

    def tutte(self) -> list[Lezione]:
        return list(self._lezioni.values())


class ClientTelegramFake:
    def __init__(self) -> None:
        self.appunti_inviati: list[tuple[Lezione, str]] = []
        self.errori_notificati: list[tuple[Lezione, str]] = []

    def invia_appunti(self, lezione: Lezione, percorso_appunti: str) -> None:
        self.appunti_inviati.append((lezione, percorso_appunti))

    def notifica_errore(self, lezione: Lezione, messaggio: str) -> None:
        self.errori_notificati.append((lezione, messaggio))
