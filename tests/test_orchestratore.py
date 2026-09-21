from __future__ import annotations

from collections.abc import Callable

from trascrizione_lezioni.adapters.fake import (
    ClientSegmentazioneFake,
    ClientTelegramFake,
    ClientTrascrizioneFake,
    ControlloGpuFake,
)
from trascrizione_lezioni.dominio import Lezione, PropostaCapitolo, Stato

from conftest import Ambiente, crea_lezione, crea_registrazione


def test_una_registrazione_arriva_a_notificata_attraversando_tutti_gli_stati() -> None:
    ambiente = Ambiente()
    ambiente.repository.salva_registrazione(crea_registrazione())

    for _ in range(5):  # ricevuta->trascritta->segmentata->elaborata->archiviata->notificata
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

    for _ in range(5):
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
    assert registrazioni["prima"].stato is Stato.SEGMENTATA
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
    assert registrazioni["a-meta"].stato is Stato.SEGMENTATA
    assert ambiente.client_trascrizione.chiamate == []


def blocco(prefisso: str, parole: int = 1300) -> str:
    """Un blocco di testo abbastanza lungo da restare un Capitolo a sé (minimo 1200 parole)."""
    return " ".join(f"{prefisso}{i}" for i in range(parole)) + "."


def _proposte_per_frasi(*frasi_inizio: str) -> Callable[[str], list[PropostaCapitolo]]:
    def comportamento(trascrizione: str) -> list[PropostaCapitolo]:
        return [PropostaCapitolo(f"Capitolo {i}", frase) for i, frase in enumerate(frasi_inizio, 1)]

    return comportamento


def test_la_segmentazione_salva_i_capitoli_e_porta_la_registrazione_a_segmentata() -> None:
    testo = f"{blocco('a')} {blocco('b')}"
    ambiente = Ambiente(
        client_trascrizione=ClientTrascrizioneFake(lambda _: testo),
        client_segmentazione=ClientSegmentazioneFake(_proposte_per_frasi("a0 a1", "b0 b1")),
    )
    registrazione = crea_registrazione()
    ambiente.repository.salva_registrazione(registrazione)

    ambiente.orchestratore.elabora_coda()  # trascrive
    ambiente.orchestratore.elabora_coda()  # segmenta

    assert registrazione.stato is Stato.SEGMENTATA
    capitoli = ambiente.repository.capitoli_della_lezione(registrazione.lezione)
    assert [c.titolo for c in capitoli] == ["Capitolo 1", "Capitolo 2"]
    assert "".join(c.testo for c in capitoli) == testo
    assert ambiente.client_telegram.errori_notificati == []


def test_se_la_segmentazione_fallisce_ripiega_su_un_capitolo_e_avvisa_l_admin() -> None:
    ambiente = Ambiente(
        client_trascrizione=ClientTrascrizioneFake(lambda _: "uno due tre. quattro cinque sei."),
        client_segmentazione=ClientSegmentazioneFake(
            _proposte_per_frasi("uno due", "parole mai dette")
        ),
    )
    registrazione = crea_registrazione()
    ambiente.repository.salva_registrazione(registrazione)

    ambiente.orchestratore.elabora_coda()
    ambiente.orchestratore.elabora_coda()

    assert registrazione.stato is Stato.SEGMENTATA
    capitoli = ambiente.repository.capitoli_della_lezione(registrazione.lezione)
    assert [c.testo for c in capitoli] == ["uno due tre. quattro cinque sei."]
    assert len(ambiente.client_telegram.errori_notificati) == 1
    assert "un unico Capitolo" in ambiente.client_telegram.errori_notificati[0][1]


def test_una_seconda_registrazione_accoda_i_suoi_capitoli_senza_toccare_i_precedenti() -> None:
    trascrizioni = {
        "/audio/prima.ogg": f"{blocco('a')} {blocco('b')}",
        "/audio/seconda.ogg": f"{blocco('c')} {blocco('d')}",
    }
    ambiente = Ambiente(
        client_trascrizione=ClientTrascrizioneFake(lambda percorso: trascrizioni[percorso]),
        client_segmentazione=ClientSegmentazioneFake(
            lambda testo: [
                PropostaCapitolo(f"{testo[:1]} 1", testo[:5]),
                PropostaCapitolo(f"{testo[:1]} 2", testo.split(". ")[1][:5]),
            ]
        ),
    )
    lezione = crea_lezione()
    prima = crea_registrazione(id="prima", lezione=lezione)
    prima.percorso_audio = "/audio/prima.ogg"
    seconda = crea_registrazione(id="seconda", lezione=lezione)
    seconda.percorso_audio = "/audio/seconda.ogg"

    ambiente.repository.salva_registrazione(prima)
    ambiente.orchestratore.elabora_coda()
    ambiente.orchestratore.elabora_coda()
    capitoli_dopo_la_prima = ambiente.repository.capitoli_della_lezione(lezione)

    ambiente.repository.salva_registrazione(seconda)
    ambiente.orchestratore.elabora_coda()
    ambiente.orchestratore.elabora_coda()

    capitoli = ambiente.repository.capitoli_della_lezione(lezione)
    assert capitoli[: len(capitoli_dopo_la_prima)] == capitoli_dopo_la_prima
    assert [c.registrazione_id for c in capitoli] == ["prima", "prima", "seconda", "seconda"]
    assert [c.titolo for c in capitoli] == ["a 1", "a 2", "c 1", "c 2"]


def test_un_errore_di_trasporto_nella_segmentazione_usa_i_tentativi_dell_orchestratore() -> None:
    def ollama_giu(_: str) -> list[PropostaCapitolo]:
        raise ConnectionError("Ollama irraggiungibile")

    ambiente = Ambiente(client_segmentazione=ClientSegmentazioneFake(ollama_giu))
    registrazione = crea_registrazione()
    registrazione.stato = Stato.TRASCRITTA
    registrazione.trascrizione = "testo"
    ambiente.repository.salva_registrazione(registrazione)

    ambiente.orchestratore.elabora_coda()
    assert registrazione.stato is Stato.TRASCRITTA  # nessun ripiego silenzioso

    ambiente.orchestratore.elabora_coda()
    assert ambiente.repository.registrazioni()[0].stato is Stato.ERRORE
    assert ambiente.repository.capitoli_della_lezione(registrazione.lezione) == []


def test_la_segmentazione_non_aspetta_la_gpu() -> None:
    ambiente = Ambiente(controllo_gpu=ControlloGpuFake(libera=False))
    registrazione = crea_registrazione()
    registrazione.stato = Stato.TRASCRITTA
    registrazione.trascrizione = "testo della lezione"
    ambiente.repository.salva_registrazione(registrazione)

    ambiente.orchestratore.elabora_coda()

    assert registrazione.stato is Stato.SEGMENTATA


def test_un_errore_nell_avviso_di_ripiego_non_fa_fallire_la_segmentazione() -> None:
    class TelegramCheFallisce(ClientTelegramFake):
        def notifica_errore(self, lezione: Lezione, messaggio: str) -> None:
            raise ConnectionError("Telegram non raggiungibile")

    ambiente = Ambiente(
        client_telegram=TelegramCheFallisce(),
        client_segmentazione=ClientSegmentazioneFake(lambda _: []),
    )
    registrazione = crea_registrazione()
    registrazione.stato = Stato.TRASCRITTA
    registrazione.trascrizione = "testo della lezione"
    ambiente.repository.salva_registrazione(registrazione)

    ambiente.orchestratore.elabora_coda()

    assert registrazione.stato is Stato.SEGMENTATA
    assert registrazione.tentativi == 0
    assert len(ambiente.client_segmentazione.chiamate) == 2  # nessuna ripetizione degli LLM
