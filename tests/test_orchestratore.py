from __future__ import annotations

from trascrizione_lezioni.adapters.fake import ClientTrascrizioneFake, ControlloGpuFake
from trascrizione_lezioni.dominio import Stato

from conftest import Ambiente, crea_lezione, crea_registrazione


def test_una_registrazione_arriva_a_notificata_attraversando_tutti_gli_stati() -> None:
    ambiente = Ambiente()
    ambiente.repository.salva_registrazione(crea_registrazione())

    for _ in range(4):  # ricevuta->trascritta->elaborata->archiviata->notificata
        ambiente.orchestratore.elabora_coda()

    registrazione_finale = ambiente.repository.registrazioni()[0]
    assert registrazione_finale.stato is Stato.NOTIFICATA
    assert ambiente.archivio.salvati
    assert ambiente.client_telegram.appunti_inviati


def test_un_job_non_viene_dispacciato_se_la_gpu_e_occupata() -> None:
    ambiente = Ambiente(controllo_gpu=ControlloGpuFake(libera=False))
    ambiente.repository.salva_registrazione(crea_registrazione())

    ambiente.orchestratore.elabora_coda()

    registrazione_finale = ambiente.repository.registrazioni()[0]
    assert registrazione_finale.stato is Stato.RICEVUTA
    assert ambiente.client_trascrizione.chiamate == []


def test_un_fallimento_persistente_viene_ritentato_due_volte_poi_va_in_errore() -> None:
    def trascrizione_che_fallisce_sempre(percorso_audio: str) -> str:
        raise RuntimeError("audio corrotto")

    ambiente = Ambiente(
        client_trascrizione=ClientTrascrizioneFake(trascrizione_che_fallisce_sempre)
    )
    ambiente.repository.salva_registrazione(crea_registrazione())

    ambiente.orchestratore.elabora_coda()
    dopo_primo_tentativo = ambiente.repository.registrazioni()[0]
    assert dopo_primo_tentativo.stato is Stato.RICEVUTA
    assert ambiente.client_telegram.errori_notificati == []

    ambiente.orchestratore.elabora_coda()
    dopo_secondo_tentativo = ambiente.repository.registrazioni()[0]
    assert dopo_secondo_tentativo.stato is Stato.ERRORE
    assert len(ambiente.client_telegram.errori_notificati) == 1


def test_un_fallimento_su_una_registrazione_non_blocca_le_altre_in_coda() -> None:
    def fallisce_solo_registrazione_problematica(percorso_audio: str) -> str:
        if "problematica" in percorso_audio:
            raise RuntimeError("audio corrotto")
        return f"trascrizione di {percorso_audio}"

    ambiente = Ambiente(
        client_trascrizione=ClientTrascrizioneFake(fallisce_solo_registrazione_problematica)
    )
    ambiente.repository.salva_registrazione(crea_registrazione(id="problematica"))
    ambiente.repository.salva_registrazione(crea_registrazione(id="sana"))

    for _ in range(4):
        ambiente.orchestratore.elabora_coda()

    registrazioni = {r.id: r for r in ambiente.repository.registrazioni()}
    assert registrazioni["sana"].stato is Stato.NOTIFICATA
    assert registrazioni["problematica"].stato is Stato.ERRORE


def test_le_registrazioni_della_stessa_lezione_avanzano_indipendentemente() -> None:
    lezione = crea_lezione()
    ambiente = Ambiente()
    ambiente.repository.salva_registrazione(crea_registrazione(id="prima", lezione=lezione))

    ambiente.orchestratore.elabora_coda()  # la prima viene trascritta appena arriva
    ambiente.repository.salva_registrazione(crea_registrazione(id="seconda", lezione=lezione))
    ambiente.orchestratore.elabora_coda()

    registrazioni = {r.id: r for r in ambiente.repository.registrazioni()}
    assert registrazioni["prima"].stato is Stato.ELABORATA
    assert registrazioni["seconda"].stato is Stato.TRASCRITTA
    assert len(ambiente.repository.lezioni()) == 1


def test_dopo_interruzione_si_riprende_solo_dalle_registrazioni_non_ancora_notificate() -> None:
    gia_notificata = crea_registrazione(id="gia-notificata")
    gia_notificata.stato = Stato.NOTIFICATA
    in_errore = crea_registrazione(id="in-errore")
    in_errore.stato = Stato.ERRORE
    a_meta = crea_registrazione(id="a-meta")
    a_meta.stato = Stato.TRASCRITTA
    a_meta.trascrizione = "testo già trascritto"

    ambiente = Ambiente()
    for registrazione in (gia_notificata, in_errore, a_meta):
        ambiente.repository.salva_registrazione(registrazione)

    ambiente.orchestratore.elabora_coda()

    registrazioni = {r.id: r for r in ambiente.repository.registrazioni()}
    assert registrazioni["gia-notificata"].stato is Stato.NOTIFICATA
    assert registrazioni["in-errore"].stato is Stato.ERRORE
    assert registrazioni["a-meta"].stato is Stato.ELABORATA
    assert ambiente.client_trascrizione.chiamate == []
