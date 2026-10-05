from __future__ import annotations

from collections.abc import Callable

from trascrizione_lezioni.adapters.fake import (
    ClientAppuntiFake,
    ClientSegmentazioneFake,
    ClientTelegramFake,
    ClientTrascrizioneFake,
    ControlloGpuFake,
)
from trascrizione_lezioni.orchestratore import Orchestratore
from trascrizione_lezioni.dominio import (
    AppuntiCapitolo,
    Capitolo,
    CapitoloTagliato,
    Lezione,
    PropostaCapitolo,
    Registrazione,
    Stato,
)

from conftest import Ambiente, crea_lezione, crea_registrazione


def test_una_registrazione_arriva_a_notificata_attraversando_tutti_gli_stati() -> None:
    ambiente = Ambiente()
    ambiente.repository.salva_registrazione(crea_registrazione())

    for _ in range(5):  # ricevuta->trascritta->segmentata->elaborata->archiviata->notificata
        ambiente.orchestratore.elabora_coda()

    registrazione_finale = ambiente.repository.registrazioni()[0]
    assert registrazione_finale.stato is Stato.NOTIFICATA
    assert ambiente.archivio.salvati
    assert ambiente.client_telegram.notifiche_appunti


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


def _senza_appunti(capitoli: list[Capitolo]) -> list[tuple[str, int, str, str]]:
    return [(c.registrazione_id, c.posizione, c.titolo, c.testo) for c in capitoli]


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
    capitoli_dopo_la_prima = _senza_appunti(ambiente.repository.capitoli_della_lezione(lezione))

    ambiente.repository.salva_registrazione(seconda)
    ambiente.orchestratore.elabora_coda()
    ambiente.orchestratore.elabora_coda()

    capitoli = ambiente.repository.capitoli_della_lezione(lezione)
    assert _senza_appunti(capitoli)[: len(capitoli_dopo_la_prima)] == capitoli_dopo_la_prima
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


def _registrazione_segmentata(
    ambiente: Ambiente, id: str, lezione: Lezione, *titoli: str
) -> Registrazione:
    registrazione = crea_registrazione(id=id, lezione=lezione)
    registrazione.stato = Stato.SEGMENTATA
    registrazione.trascrizione = "testo"
    ambiente.repository.salva_registrazione(registrazione)
    ambiente.repository.sostituisci_capitoli(
        registrazione, [CapitoloTagliato(titolo, f"testo di {titolo}") for titolo in titoli]
    )
    return registrazione


def test_gli_appunti_si_generano_per_ogni_capitolo_e_poi_il_quadro_generale() -> None:
    ambiente = Ambiente()
    lezione = crea_lezione()
    registrazione = _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi", "Funzioni")

    ambiente.orchestratore.elabora_coda()

    assert registrazione.stato is Stato.ELABORATA
    assert ambiente.client_appunti.chiamate_capitolo == [
        ("Insiemi", "testo di Insiemi", "Analisi 1"),
        ("Funzioni", "testo di Funzioni", "Analisi 1"),
    ]
    capitoli = ambiente.repository.capitoli_della_lezione(lezione)
    assert all(c.appunti is not None for c in capitoli)
    assert len(ambiente.client_appunti.chiamate_quadro) == 1
    assert ambiente.client_appunti.chiamate_quadro[0][2] == [
        ("Insiemi", "Riassunto di Insiemi."),
        ("Funzioni", "Riassunto di Funzioni."),
    ]
    assert lezione.quadro_generale == "Lezione di Analisi 1 su 2 argomenti."


def test_una_nuova_registrazione_genera_appunti_solo_per_i_suoi_capitoli_e_ricalcola_il_quadro() -> None:
    ambiente = Ambiente()
    lezione = crea_lezione()
    _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi")
    ambiente.orchestratore.elabora_coda()  # r1 -> ELABORATA
    ambiente.client_appunti.chiamate_capitolo.clear()

    _registrazione_segmentata(ambiente, "r2", lezione, "Funzioni")
    ambiente.orchestratore.elabora_coda()

    assert [c[0] for c in ambiente.client_appunti.chiamate_capitolo] == ["Funzioni"]
    ultimo_quadro = ambiente.client_appunti.chiamate_quadro[-1]
    assert [titolo for titolo, _ in ultimo_quadro[2]] == ["Insiemi", "Funzioni"]
    assert lezione.quadro_generale == "Lezione di Analisi 1 su 2 argomenti."


def test_dopo_un_errore_a_meta_i_capitoli_gia_elaborati_non_vengono_rigenerati() -> None:
    fallisce_su_funzioni = {"attivo": True}

    def appunti(titolo: str, testo: str, materia: str) -> AppuntiCapitolo:
        if titolo == "Funzioni" and fallisce_su_funzioni["attivo"]:
            raise RuntimeError("modello non disponibile")
        return AppuntiCapitolo(riassunto=f"Riassunto di {titolo}.")

    ambiente = Ambiente(client_appunti=ClientAppuntiFake(appunti_capitolo=appunti))
    lezione = crea_lezione()
    registrazione = _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi", "Funzioni")

    ambiente.orchestratore.elabora_coda()
    assert registrazione.stato is Stato.SEGMENTATA
    assert registrazione.tentativi == 1

    fallisce_su_funzioni["attivo"] = False
    ambiente.orchestratore.elabora_coda()

    assert ambiente.repository.registrazioni()[0].stato is Stato.ELABORATA
    titoli_chiamati = [c[0] for c in ambiente.client_appunti.chiamate_capitolo]
    assert titoli_chiamati == ["Insiemi", "Funzioni", "Funzioni"]  # Insiemi una volta sola


def test_l_archiviazione_scrive_un_solo_file_per_lezione_ricomposto_dai_dati() -> None:
    ambiente = Ambiente()
    lezione = crea_lezione()
    r1 = _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi")
    ambiente.orchestratore.elabora_coda()  # ELABORATA
    ambiente.orchestratore.elabora_coda()  # ARCHIVIATA

    assert r1.stato is Stato.ARCHIVIATA
    assert list(ambiente.archivio.salvati) == ["archivio/Analisi 1/2026-03-05.md"]
    primo = ambiente.archivio.salvati["archivio/Analisi 1/2026-03-05.md"]
    assert "## 1. Insiemi" in primo

    r2 = _registrazione_segmentata(ambiente, "r2", lezione, "Funzioni")
    chiamate_prima = len(ambiente.client_appunti.chiamate_capitolo)
    for _ in range(2):
        ambiente.orchestratore.elabora_coda()

    assert r2.stato is Stato.ARCHIVIATA
    assert list(ambiente.archivio.salvati) == ["archivio/Analisi 1/2026-03-05.md"]  # stesso file
    secondo = ambiente.archivio.salvati["archivio/Analisi 1/2026-03-05.md"]
    assert "## 1. Insiemi" in secondo and "## 2. Funzioni" in secondo
    # Archiviare non chiama mai il LLM: solo il passo di elaborazione lo fa.
    assert len(ambiente.client_appunti.chiamate_capitolo) == chiamate_prima + 1
    assert r1.percorso_appunti == r2.percorso_appunti


def test_il_file_di_una_lezione_non_mostra_i_capitoli_di_una_registrazione_non_ancora_elaborata() -> None:
    ambiente = Ambiente()
    lezione = crea_lezione()
    _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi")
    ambiente.orchestratore.elabora_coda()  # r1 ELABORATA
    _registrazione_segmentata(ambiente, "r2", lezione, "Funzioni")  # r2 ancora SEGMENTATA

    ambiente.orchestratore.elabora_coda()  # r1 archiviata mentre r2 viene elaborata

    contenuto = ambiente.archivio.salvati["archivio/Analisi 1/2026-03-05.md"]
    assert "Insiemi" in contenuto
    assert "Funzioni" not in contenuto


def test_una_registrazione_gia_elaborata_col_vecchio_flusso_riceve_gli_appunti_mancanti_prima_dell_archiviazione() -> None:
    ambiente = Ambiente()
    lezione = crea_lezione()
    registrazione = _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi")
    registrazione.stato = Stato.ELABORATA  # come dopo il deploy: Capitoli ma niente appunti

    ambiente.orchestratore.elabora_coda()

    assert registrazione.stato is Stato.ARCHIVIATA
    assert [c[0] for c in ambiente.client_appunti.chiamate_capitolo] == ["Insiemi"]
    contenuto = ambiente.archivio.salvati["archivio/Analisi 1/2026-03-05.md"]
    assert "## 1. Insiemi" in contenuto


def test_non_si_archivia_mai_un_file_senza_capitoli_elaborati() -> None:
    ambiente = Ambiente()
    registrazione = crea_registrazione()
    registrazione.stato = Stato.ELABORATA  # nessun Capitolo salvato
    ambiente.repository.salva_registrazione(registrazione)

    ambiente.orchestratore.elabora_coda()

    assert ambiente.archivio.salvati == {}
    assert registrazione.stato is Stato.ELABORATA
    assert registrazione.tentativi == 1


def test_arriva_una_notifica_per_registrazione_con_i_soli_titoli_dei_suoi_capitoli() -> None:
    ambiente = Ambiente()
    lezione = crea_lezione()
    r1 = _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi", "Funzioni")

    for _ in range(3):  # SEGMENTATA -> ELABORATA -> ARCHIVIATA -> NOTIFICATA
        ambiente.orchestratore.elabora_coda()

    assert r1.stato is Stato.NOTIFICATA
    assert ambiente.client_telegram.notifiche_appunti == [(lezione, ["Insiemi", "Funzioni"])]

    _registrazione_segmentata(ambiente, "r2", lezione, "Limiti")
    for _ in range(3):
        ambiente.orchestratore.elabora_coda()

    assert ambiente.client_telegram.notifiche_appunti == [
        (lezione, ["Insiemi", "Funzioni"]),
        (lezione, ["Limiti"]),
    ]


def test_la_notifica_parte_solo_dopo_l_archiviazione() -> None:
    ambiente = Ambiente()
    lezione = crea_lezione()
    _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi")

    ambiente.orchestratore.elabora_coda()  # ELABORATA
    ambiente.orchestratore.elabora_coda()  # ARCHIVIATA
    assert ambiente.client_telegram.notifiche_appunti == []
    assert ambiente.archivio.salvati

    ambiente.orchestratore.elabora_coda()  # NOTIFICATA
    assert len(ambiente.client_telegram.notifiche_appunti) == 1


def test_una_notifica_fallita_viene_ritentata_senza_riarchiviare() -> None:
    class TelegramGiu(ClientTelegramFake):
        def notifica_appunti(
            self, lezione: Lezione, titoli: list[str], link: str | None
        ) -> None:
            raise ConnectionError("Telegram non raggiungibile")

    ambiente = Ambiente(client_telegram=TelegramGiu())
    registrazione = _registrazione_segmentata(ambiente, "r1", crea_lezione(), "Insiemi")
    for _ in range(3):
        ambiente.orchestratore.elabora_coda()

    assert ambiente.repository.registrazioni()[0].stato is Stato.ARCHIVIATA
    assert registrazione.tentativi == 1


def _ambiente_con_sito(url_sito: str | None) -> Ambiente:
    ambiente = Ambiente()
    ambiente.orchestratore = Orchestratore(
        controllo_gpu=ambiente.controllo_gpu,
        client_trascrizione=ambiente.client_trascrizione,
        client_segmentazione=ambiente.client_segmentazione,
        client_appunti=ambiente.client_appunti,
        archivio=ambiente.archivio,
        repository=ambiente.repository,
        client_telegram=ambiente.client_telegram,
        url_sito=url_sito,
    )
    return ambiente


def test_la_notifica_ha_il_link_al_primo_capitolo_della_registrazione() -> None:
    ambiente = _ambiente_con_sito("https://studio.example")
    lezione = crea_lezione()
    _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi", "Funzioni")

    for _ in range(3):
        ambiente.orchestratore.elabora_coda()

    assert ambiente.client_telegram.link_appunti == ["https://studio.example/capitolo/r1/0"]


def test_il_link_della_seconda_registrazione_porta_ai_suoi_capitoli_non_a_quelli_della_prima() -> None:
    ambiente = _ambiente_con_sito("https://studio.example/")  # la barra finale non raddoppia
    lezione = crea_lezione()
    _registrazione_segmentata(ambiente, "r1", lezione, "Insiemi")
    for _ in range(3):
        ambiente.orchestratore.elabora_coda()
    _registrazione_segmentata(ambiente, "r2", lezione, "Limiti", "Derivate")
    for _ in range(3):
        ambiente.orchestratore.elabora_coda()

    assert ambiente.client_telegram.link_appunti == [
        "https://studio.example/capitolo/r1/0",
        "https://studio.example/capitolo/r2/0",
    ]


def test_senza_indirizzo_del_sito_la_notifica_parte_senza_link() -> None:
    ambiente = _ambiente_con_sito(None)
    _registrazione_segmentata(ambiente, "r1", crea_lezione(), "Insiemi")

    for _ in range(3):
        ambiente.orchestratore.elabora_coda()

    assert ambiente.client_telegram.link_appunti == [None]
    assert len(ambiente.client_telegram.notifiche_appunti) == 1
