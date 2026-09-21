from __future__ import annotations

from datetime import date

from trascrizione_lezioni.adapters.fake import (
    ArchivioFake,
    ClientAppuntiFake,
    ClientSegmentazioneFake,
    ClientTelegramFake,
    ClientTrascrizioneFake,
    ControlloGpuFake,
    RepositoryFake,
)
from trascrizione_lezioni.dominio import Lezione, Registrazione
from trascrizione_lezioni.orchestratore import Orchestratore


def crea_lezione(id: str = "lezione-1", materia: str = "Analisi 1") -> Lezione:
    return Lezione(id=id, materia=materia, data=date(2026, 3, 5), chat_id="fratello-1")


def crea_registrazione(
    id: str = "registrazione-1", lezione: Lezione | None = None
) -> Registrazione:
    return Registrazione(
        id=id,
        lezione=lezione or crea_lezione(),
        percorso_audio=f"/audio/{id}.ogg",
    )


class Ambiente:
    """Raccoglie l'Orchestratore e i suoi 7 fake, per ispezionarli nei test."""

    def __init__(
        self,
        *,
        controllo_gpu: ControlloGpuFake | None = None,
        client_trascrizione: ClientTrascrizioneFake | None = None,
        client_segmentazione: ClientSegmentazioneFake | None = None,
        client_appunti: ClientAppuntiFake | None = None,
        archivio: ArchivioFake | None = None,
        repository: RepositoryFake | None = None,
        client_telegram: ClientTelegramFake | None = None,
    ) -> None:
        self.controllo_gpu = controllo_gpu or ControlloGpuFake()
        self.client_trascrizione = client_trascrizione or ClientTrascrizioneFake()
        self.client_segmentazione = client_segmentazione or ClientSegmentazioneFake()
        self.client_appunti = client_appunti or ClientAppuntiFake()
        self.archivio = archivio or ArchivioFake()
        self.repository = repository or RepositoryFake()
        self.client_telegram = client_telegram or ClientTelegramFake()
        self.orchestratore = Orchestratore(
            controllo_gpu=self.controllo_gpu,
            client_trascrizione=self.client_trascrizione,
            client_segmentazione=self.client_segmentazione,
            client_appunti=self.client_appunti,
            archivio=self.archivio,
            repository=self.repository,
            client_telegram=self.client_telegram,
        )
