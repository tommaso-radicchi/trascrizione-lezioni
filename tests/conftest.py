from __future__ import annotations

from datetime import date

from trascrizione_lezioni.adapters.fake import (
    ArchivioFake,
    ClientAppuntiFake,
    ClientTelegramFake,
    ClientTrascrizioneFake,
    ControlloGpuFake,
    RepositoryFake,
)
from trascrizione_lezioni.dominio import Lezione
from trascrizione_lezioni.orchestratore import Orchestratore


def crea_lezione(id: str = "lezione-1", materia: str = "Analisi 1") -> Lezione:
    return Lezione(
        id=id,
        materia=materia,
        data=date(2026, 3, 5),
        percorso_audio=f"/audio/{id}.ogg",
    )


class Ambiente:
    """Raccoglie l'Orchestratore e i suoi 6 fake, per ispezionarli nei test."""

    def __init__(
        self,
        *,
        controllo_gpu: ControlloGpuFake | None = None,
        client_trascrizione: ClientTrascrizioneFake | None = None,
        client_appunti: ClientAppuntiFake | None = None,
        archivio: ArchivioFake | None = None,
        repository: RepositoryFake | None = None,
        client_telegram: ClientTelegramFake | None = None,
    ) -> None:
        self.controllo_gpu = controllo_gpu or ControlloGpuFake()
        self.client_trascrizione = client_trascrizione or ClientTrascrizioneFake()
        self.client_appunti = client_appunti or ClientAppuntiFake()
        self.archivio = archivio or ArchivioFake()
        self.repository = repository or RepositoryFake()
        self.client_telegram = client_telegram or ClientTelegramFake()
        self.orchestratore = Orchestratore(
            controllo_gpu=self.controllo_gpu,
            client_trascrizione=self.client_trascrizione,
            client_appunti=self.client_appunti,
            archivio=self.archivio,
            repository=self.repository,
            client_telegram=self.client_telegram,
        )
