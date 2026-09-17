"""Il core dell'Orchestratore: decide il prossimo passo per ogni Lezione in coda."""

from __future__ import annotations

from .dominio import Lezione, Stato
from .porte import (
    Archivio,
    ClientAppunti,
    ClientTelegram,
    ClientTrascrizione,
    ControlloGpu,
    Repository,
)

TENTATIVI_MASSIMI = 2

STATI_CHE_RICHIEDONO_GPU = {Stato.RICEVUTA, Stato.TRASCRITTA}


class Orchestratore:
    def __init__(
        self,
        *,
        controllo_gpu: ControlloGpu,
        client_trascrizione: ClientTrascrizione,
        client_appunti: ClientAppunti,
        archivio: Archivio,
        repository: Repository,
        client_telegram: ClientTelegram,
    ) -> None:
        self._controllo_gpu = controllo_gpu
        self._client_trascrizione = client_trascrizione
        self._client_appunti = client_appunti
        self._archivio = archivio
        self._repository = repository
        self._client_telegram = client_telegram

    def elabora_coda(self) -> None:
        for lezione in self._repository.da_processare():
            self._avanza(lezione)

    def _avanza(self, lezione: Lezione) -> None:
        if lezione.stato in STATI_CHE_RICHIEDONO_GPU and not self._controllo_gpu.libera():
            return

        try:
            self._esegui_passo(lezione)
        except Exception as errore:
            self._registra_fallimento(lezione, errore)
            return

        lezione.tentativi = 0
        self._repository.salva(lezione)

    def _esegui_passo(self, lezione: Lezione) -> None:
        if lezione.stato is Stato.RICEVUTA:
            lezione.trascrizione = self._client_trascrizione.trascrivi(lezione.percorso_audio)
            lezione.stato = Stato.TRASCRITTA
        elif lezione.stato is Stato.TRASCRITTA:
            assert lezione.trascrizione is not None
            lezione.appunti_markdown = self._client_appunti.genera_appunti(
                lezione.trascrizione, lezione.materia
            )
            lezione.stato = Stato.ELABORATA
        elif lezione.stato is Stato.ELABORATA:
            assert lezione.appunti_markdown is not None
            lezione.percorso_appunti = self._archivio.salva(lezione, lezione.appunti_markdown)
            lezione.stato = Stato.ARCHIVIATA
        elif lezione.stato is Stato.ARCHIVIATA:
            assert lezione.percorso_appunti is not None
            self._client_telegram.invia_appunti(lezione, lezione.percorso_appunti)
            lezione.stato = Stato.NOTIFICATA

    def _registra_fallimento(self, lezione: Lezione, errore: Exception) -> None:
        lezione.tentativi += 1
        if lezione.tentativi >= TENTATIVI_MASSIMI:
            lezione.stato = Stato.ERRORE
            self._client_telegram.notifica_errore(lezione, str(errore))
        self._repository.salva(lezione)
