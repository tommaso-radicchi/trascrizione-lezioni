"""Il core dell'Orchestratore: decide il prossimo passo per ogni Registrazione in coda."""

from __future__ import annotations

import logging

from .dominio import Registrazione, Stato
from .segmentazione import segmenta
from .porte import (
    Archivio,
    ClientAppunti,
    ClientSegmentazione,
    ClientTelegram,
    ClientTrascrizione,
    ControlloGpu,
    Repository,
)

logger = logging.getLogger(__name__)

TENTATIVI_MASSIMI = 2

# Solo Whisper usa la GPU dell'MSI: segmentazione e appunti vanno su Ollama (Mac Mini).
STATI_CHE_RICHIEDONO_GPU = {Stato.RICEVUTA}


class Orchestratore:
    def __init__(
        self,
        *,
        controllo_gpu: ControlloGpu,
        client_trascrizione: ClientTrascrizione,
        client_segmentazione: ClientSegmentazione,
        client_appunti: ClientAppunti,
        archivio: Archivio,
        repository: Repository,
        client_telegram: ClientTelegram,
    ) -> None:
        self._controllo_gpu = controllo_gpu
        self._client_trascrizione = client_trascrizione
        self._client_segmentazione = client_segmentazione
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
            risultato = segmenta(registrazione.trascrizione, self._client_segmentazione)
            self._repository.sostituisci_capitoli(registrazione, risultato.capitoli)
            if risultato.motivo_ripiego is not None:
                self._avvisa_ripiego(registrazione, risultato.motivo_ripiego)
            registrazione.stato = Stato.SEGMENTATA
        elif registrazione.stato is Stato.SEGMENTATA:
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

    def _avvisa_ripiego(self, registrazione: Registrazione, motivo: str) -> None:
        # Best effort: la segmentazione è già riuscita e salvata, un errore dell'avviso non
        # deve contare come fallimento del passo (rifarebbe anche le chiamate al LLM).
        try:
            self._client_telegram.notifica_errore(
                registrazione.lezione,
                f"Segmentazione in Capitoli non riuscita, uso un unico Capitolo: {motivo}",
            )
        except Exception:
            logger.exception("Avviso di ripiego della segmentazione non inviato")

    def _registra_fallimento(self, registrazione: Registrazione, errore: Exception) -> None:
        registrazione.tentativi += 1
        if registrazione.tentativi >= TENTATIVI_MASSIMI:
            registrazione.stato = Stato.ERRORE
            self._client_telegram.notifica_errore(registrazione.lezione, str(errore))
        self._repository.salva_registrazione(registrazione)
