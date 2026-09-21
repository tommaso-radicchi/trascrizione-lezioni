"""Implementazioni finte/in-memory delle 7 porte, per test e per l'harness di sviluppo."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date

from ..dominio import (
    AppuntiCapitolo,
    Capitolo,
    CapitoloTagliato,
    Domanda,
    Lezione,
    PropostaCapitolo,
    Registrazione,
    Stato,
    StatoComprensione,
)
from ..studio import DettaglioCapitolo, LezioneStudio


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


class ClientSegmentazioneFake:
    def __init__(
        self, comportamento: Callable[[str], list[PropostaCapitolo]] | None = None
    ) -> None:
        self._comportamento = comportamento or (
            lambda trascrizione: [
                PropostaCapitolo("Capitolo", " ".join(trascrizione.split()[:4]) or "-")
            ]
        )
        self.chiamate: list[str] = []

    def proponi_capitoli(self, trascrizione: str) -> list[PropostaCapitolo]:
        self.chiamate.append(trascrizione)
        return self._comportamento(trascrizione)


class ClientAppuntiFake:
    def __init__(
        self,
        appunti_capitolo: Callable[[str, str, str], AppuntiCapitolo] | None = None,
        quadro_generale: Callable[[str, date, list[tuple[str, str]]], str] | None = None,
    ) -> None:
        self._appunti_capitolo = appunti_capitolo or (
            lambda titolo, testo, materia: AppuntiCapitolo(
                riassunto=f"Riassunto di {titolo}.",
                punti_chiave=[f"Punto chiave di {titolo}"],
                domande=[Domanda(f"Domanda su {titolo}?", "Risposta breve.")],
            )
        )
        self._quadro_generale = quadro_generale or (
            lambda materia, data, riassunti: f"Lezione di {materia} su {len(riassunti)} argomenti."
        )
        self.chiamate_capitolo: list[tuple[str, str, str]] = []
        self.chiamate_quadro: list[tuple[str, date, list[tuple[str, str]]]] = []

    def genera_appunti_capitolo(self, titolo: str, testo: str, materia: str) -> AppuntiCapitolo:
        self.chiamate_capitolo.append((titolo, testo, materia))
        return self._appunti_capitolo(titolo, testo, materia)

    def genera_quadro_generale(
        self, materia: str, data: date, riassunti: list[tuple[str, str]]
    ) -> str:
        self.chiamate_quadro.append((materia, data, riassunti))
        return self._quadro_generale(materia, data, riassunti)


class ArchivioFake:
    def __init__(self) -> None:
        self.salvati: dict[str, str] = {}

    def salva(self, lezione: Lezione, appunti_markdown: str) -> str:
        percorso = f"archivio/{lezione.materia}/{lezione.data.isoformat()}.md"
        self.salvati[percorso] = appunti_markdown
        return percorso


class RepositoryFake:
    def __init__(self, registrazioni: list[Registrazione] | None = None) -> None:
        self._lezioni: dict[str, Lezione] = {}
        self._registrazioni: dict[str, Registrazione] = {}
        self._capitoli: dict[str, list[CapitoloTagliato]] = {}
        self._appunti: dict[tuple[str, int], AppuntiCapitolo] = {}
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

    def sostituisci_capitoli(
        self, registrazione: Registrazione, capitoli: list[CapitoloTagliato]
    ) -> None:
        self._capitoli[registrazione.id] = list(capitoli)
        self._appunti = {k: v for k, v in self._appunti.items() if k[0] != registrazione.id}

    def salva_appunti(self, capitolo: Capitolo, appunti: AppuntiCapitolo) -> None:
        self._appunti[(capitolo.registrazione_id, capitolo.posizione)] = appunti

    def salva_quadro_generale(self, lezione: Lezione, quadro_generale: str) -> None:
        # Come su Postgres: scrive sulla Lezione salvata, non sulla copia in mano al chiamante.
        self._lezioni[lezione.id].quadro_generale = quadro_generale

    def capitoli_della_lezione(self, lezione: Lezione) -> list[Capitolo]:
        return [
            Capitolo(
                registrazione.id,
                posizione,
                capitolo.titolo,
                capitolo.testo,
                self._appunti.get((registrazione.id, posizione)),
            )
            for registrazione in self._registrazioni.values()
            if registrazione.lezione.id == lezione.id
            for posizione, capitolo in enumerate(self._capitoli.get(registrazione.id, []))
        ]

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
        self.notifiche_appunti: list[tuple[Lezione, list[str]]] = []
        self.errori_notificati: list[tuple[Lezione, str]] = []
        self.materie_richieste: list[tuple[str, list[str]]] = []
        self.conferme_inviate: list[str] = []

    def notifica_appunti(self, lezione: Lezione, titoli_nuovi: list[str]) -> None:
        self.notifiche_appunti.append((lezione, list(titoli_nuovi)))

    def notifica_errore(self, lezione: Lezione, messaggio: str) -> None:
        self.errori_notificati.append((lezione, messaggio))

    def chiedi_materia(self, chat_id: str, materie: list[str]) -> None:
        self.materie_richieste.append((chat_id, materie))

    def conferma_ricezione(self, chat_id: str) -> None:
        self.conferme_inviate.append(chat_id)


class LetturaStudioFake:
    """Il modello di lettura del sito, in memoria: si costruisce già in forma di
    Lezioni e Capitoli, con testo e Appunti per il dettaglio."""

    def __init__(
        self,
        lezioni: list[LezioneStudio],
        dettagli: dict[tuple[str, int], tuple[str, AppuntiCapitolo]] | None = None,
    ) -> None:
        self._lezioni = lezioni
        self._dettagli = dettagli or {}

    def lezioni(self) -> list[LezioneStudio]:
        return sorted(self._lezioni, key=lambda lezione: (lezione.data, lezione.id))

    def dettaglio_capitolo(
        self, registrazione_id: str, posizione: int
    ) -> DettaglioCapitolo | None:
        for lezione in self._lezioni:
            for capitolo in lezione.capitoli:
                if capitolo.registrazione_id == registrazione_id and capitolo.posizione == posizione:
                    testo, appunti = self._dettagli.get(
                        (registrazione_id, posizione),
                        (f"testo di {capitolo.titolo}", AppuntiCapitolo(riassunto=capitolo.titolo)),
                    )
                    return DettaglioCapitolo(lezione, capitolo, testo, appunti)
        return None

    def imposta_stato(
        self, registrazione_id: str, posizione: int, stato: StatoComprensione
    ) -> bool:
        for lezione in self._lezioni:
            for indice, capitolo in enumerate(lezione.capitoli):
                if capitolo.registrazione_id == registrazione_id and capitolo.posizione == posizione:
                    lezione.capitoli[indice] = replace(capitolo, stato=stato)
                    return True
        return False
