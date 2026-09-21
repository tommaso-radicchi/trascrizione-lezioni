"""Il core dell'Orchestratore: decide il prossimo passo per ogni Registrazione in coda."""

from __future__ import annotations

import logging

from .dominio import Registrazione, Stato
from .composizione import componi_markdown
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
            self._genera_appunti(registrazione)
            registrazione.stato = Stato.ELABORATA
        elif registrazione.stato is Stato.ELABORATA:
            registrazione.percorso_appunti = self._archivia(registrazione)
            registrazione.stato = Stato.ARCHIVIATA
        elif registrazione.stato is Stato.ARCHIVIATA:
            titoli_nuovi = [
                capitolo.titolo
                for capitolo in self._repository.capitoli_della_lezione(lezione)
                if capitolo.registrazione_id == registrazione.id
            ]
            self._client_telegram.notifica_appunti(lezione, titoli_nuovi)
            registrazione.stato = Stato.NOTIFICATA

    def _genera_appunti(self, registrazione: Registrazione) -> None:
        """Gli Appunti si generano una sola volta per Capitolo: dopo un errore a metà,
        al tentativo successivo si riprende dai Capitoli che ancora ne sono privi."""
        lezione = registrazione.lezione
        for capitolo in self._repository.capitoli_della_lezione(lezione):
            if capitolo.registrazione_id != registrazione.id or capitolo.appunti is not None:
                continue
            appunti = self._client_appunti.genera_appunti_capitolo(
                capitolo.titolo, capitolo.testo, lezione.materia
            )
            self._repository.salva_appunti(capitolo, appunti)

        # Il quadro generale si ricalcola dai soli riassunti di tutti i Capitoli elaborati.
        riassunti = [
            (capitolo.titolo, capitolo.appunti.riassunto)
            for capitolo in self._repository.capitoli_della_lezione(lezione)
            if capitolo.appunti is not None
        ]
        quadro = self._client_appunti.genera_quadro_generale(
            lezione.materia, lezione.data, riassunti
        )
        self._repository.salva_quadro_generale(lezione, quadro)

    def _archivia(self, registrazione: Registrazione) -> str:
        """Ricompone il file della Lezione dai dati salvati, senza chiamare il LLM
        (salvo per i Capitoli di questa Registrazione rimasti senza Appunti)."""
        lezione = registrazione.lezione
        capitoli = self._repository.capitoli_della_lezione(lezione)
        if any(c.registrazione_id == registrazione.id and c.appunti is None for c in capitoli):
            # Una Registrazione elaborata da una versione precedente: si completa.
            self._genera_appunti(registrazione)
            capitoli = self._repository.capitoli_della_lezione(lezione)
        if not any(c.appunti is not None for c in capitoli):
            # Mai sovrascrivere il file di una Lezione con un documento vuoto.
            raise RuntimeError("Nessun Capitolo con Appunti da archiviare")

        # Riletta: la copia in mano a questa Registrazione può non avere l'ultimo quadro generale.
        lezione_aggiornata = self._repository.trova_lezione(lezione.materia, lezione.data) or lezione
        return self._archivio.salva(lezione_aggiornata, componi_markdown(lezione_aggiornata, capitoli))

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
