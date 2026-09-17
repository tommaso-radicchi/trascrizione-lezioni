from __future__ import annotations

from trascrizione_lezioni.adapters.fake import ClientTrascrizioneFake, ControlloGpuFake
from trascrizione_lezioni.dominio import Stato

from conftest import Ambiente, crea_lezione


def test_una_lezione_arriva_a_notificata_attraversando_tutti_gli_stati() -> None:
    ambiente = Ambiente()
    lezione = crea_lezione()
    ambiente.repository.salva(lezione)

    for _ in range(4):  # ricevuta->trascritta->elaborata->archiviata->notificata
        ambiente.orchestratore.elabora_coda()

    lezione_finale = ambiente.repository.tutte()[0]
    assert lezione_finale.stato is Stato.NOTIFICATA
    assert ambiente.archivio.salvati
    assert ambiente.client_telegram.appunti_inviati


def test_un_job_non_viene_dispacciato_se_la_gpu_e_occupata() -> None:
    ambiente = Ambiente(controllo_gpu=ControlloGpuFake(libera=False))
    lezione = crea_lezione()
    ambiente.repository.salva(lezione)

    ambiente.orchestratore.elabora_coda()

    lezione_finale = ambiente.repository.tutte()[0]
    assert lezione_finale.stato is Stato.RICEVUTA
    assert ambiente.client_trascrizione.chiamate == []


def test_un_fallimento_persistente_viene_ritentato_due_volte_poi_va_in_errore() -> None:
    def trascrizione_che_fallisce_sempre(percorso_audio: str) -> str:
        raise RuntimeError("audio corrotto")

    ambiente = Ambiente(
        client_trascrizione=ClientTrascrizioneFake(trascrizione_che_fallisce_sempre)
    )
    lezione = crea_lezione()
    ambiente.repository.salva(lezione)

    ambiente.orchestratore.elabora_coda()
    lezione_dopo_primo_tentativo = ambiente.repository.tutte()[0]
    assert lezione_dopo_primo_tentativo.stato is Stato.RICEVUTA
    assert ambiente.client_telegram.errori_notificati == []

    ambiente.orchestratore.elabora_coda()
    lezione_dopo_secondo_tentativo = ambiente.repository.tutte()[0]
    assert lezione_dopo_secondo_tentativo.stato is Stato.ERRORE
    assert len(ambiente.client_telegram.errori_notificati) == 1


def test_un_fallimento_su_una_lezione_non_blocca_le_altre_in_coda() -> None:
    def fallisce_solo_lezione_problematica(percorso_audio: str) -> str:
        if "problematica" in percorso_audio:
            raise RuntimeError("audio corrotto")
        return f"trascrizione di {percorso_audio}"

    ambiente = Ambiente(
        client_trascrizione=ClientTrascrizioneFake(fallisce_solo_lezione_problematica)
    )
    lezione_problematica = crea_lezione(id="problematica")
    lezione_sana = crea_lezione(id="sana")
    ambiente.repository.salva(lezione_problematica)
    ambiente.repository.salva(lezione_sana)

    for _ in range(4):
        ambiente.orchestratore.elabora_coda()

    lezioni = {l.id: l for l in ambiente.repository.tutte()}
    assert lezioni["sana"].stato is Stato.NOTIFICATA
    assert lezioni["problematica"].stato is Stato.ERRORE


def test_dopo_interruzione_si_riprende_solo_dalle_lezioni_non_ancora_notificate() -> None:
    lezione_gia_notificata = crea_lezione(id="gia-notificata")
    lezione_gia_notificata.stato = Stato.NOTIFICATA
    lezione_in_errore = crea_lezione(id="in-errore")
    lezione_in_errore.stato = Stato.ERRORE
    lezione_a_meta = crea_lezione(id="a-meta")
    lezione_a_meta.stato = Stato.TRASCRITTA
    lezione_a_meta.trascrizione = "testo già trascritto"

    ambiente = Ambiente()
    for lezione in (lezione_gia_notificata, lezione_in_errore, lezione_a_meta):
        ambiente.repository.salva(lezione)

    ambiente.orchestratore.elabora_coda()

    lezioni = {l.id: l for l in ambiente.repository.tutte()}
    assert lezioni["gia-notificata"].stato is Stato.NOTIFICATA
    assert lezioni["in-errore"].stato is Stato.ERRORE
    assert lezioni["a-meta"].stato is Stato.ELABORATA
    assert ambiente.client_trascrizione.chiamate == []
