"""Il core dell'Orchestratore: decide il prossimo passo per ogni Registrazione in coda."""

from __future__ import annotations

from .dominio import Registrazione, Stato
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
        for registrazione in self._repository.registrazioni_da_processare():
            self._avanza(registrazione)

    def _avanza(self, registrazione: Registrazione) -> None:
        if registrazione.stato in STATI_CHE_RICHIEDONO_GPU and not self._controllo_gpu.libera():
            return

        try:
            self._esegui_passo(registrazione)
        except Exception as errore:
            self._registra_fallimento(registrazione, errore)
            return

        registrazione.tentativi = 0
        self._repository.salva_registrazione(registrazione)

    def _esegui_passo(self, registrazione: Registrazione) -> None:
        lezione = registrazione.lezione
        if registrazione.stato is Stato.RICEVUTA:
            registrazione.trascrizione = self._client_trascrizione.trascrivi(
                registrazione.percorso_audio
            )
            registrazione.stato = Stato.TRASCRITTA
        elif registrazione.stato is Stato.TRASCRITTA:
            assert registrazione.trascrizione is not None
            registrazione.appunti_markdown = self._client_appunti.genera_appunti(
                registrazione.trascrizione, lezione.materia, lezione.data
            )
            registrazione.stato = Stato.ELABORATA
        elif registrazione.stato is Stato.ELABORATA:
            assert registrazione.appunti_markdown is not None
            registrazione.percorso_appunti = self._archivio.salva(
                registrazione, registrazione.appunti_markdown
            )
            registrazione.stato = Stato.ARCHIVIATA
        elif registrazione.stato is Stato.ARCHIVIATA:
            assert registrazione.percorso_appunti is not None
            self._client_telegram.invia_appunti(lezione, registrazione.percorso_appunti)
            registrazione.stato = Stato.NOTIFICATA

    def _registra_fallimento(self, registrazione: Registrazione, errore: Exception) -> None:
        registrazione.tentativi += 1
        if registrazione.tentativi >= TENTATIVI_MASSIMI:
            registrazione.stato = Stato.ERRORE
            self._client_telegram.notifica_errore(registrazione.lezione, str(errore))
        self._repository.salva_registrazione(registrazione)
