"""Test di contratto per RepositoryPostgres: gira contro un Postgres reale
(docker compose up postgres). Fuori dal seam principale dell'Orchestratore,
per policy dallo spec (vedi issue #1, sezione Testing Decisions).

Usa DATABASE_URL_TEST, mai DATABASE_URL: ogni test svuota le tabelle `lezioni` e `registrazioni`,
quindi deve puntare a un database dedicato (il cui nome finisce in `_test`)."""

from __future__ import annotations

from datetime import date, timedelta

import psycopg
import pytest

from trascrizione_lezioni.adapters.postgres import ElaborazioneInCorso, RepositoryPostgres
from trascrizione_lezioni.dominio import (
    AppuntiCapitolo,
    CapitoloTagliato,
    Domanda,
    Lezione,
    Registrazione,
    Stato,
    Termine,
)

def crea_registrazione(
    id: str,
    *,
    materia: str = "Analisi 1",
    data: date = date(2026, 3, 5),
    lezione_id: str | None = None,
    **campi: object,
) -> Registrazione:
    lezione = Lezione(
        id=lezione_id or f"lezione-{id}", materia=materia, data=data, chat_id="fratello-1"
    )
    return Registrazione(
        id=id,
        lezione=lezione,
        percorso_audio=f"/audio/{id}.ogg",
        **campi,  # type: ignore[arg-type]
    )


def salva(repository: RepositoryPostgres, registrazione: Registrazione) -> None:
    repository.salva_lezione(registrazione.lezione)
    repository.salva_registrazione(registrazione)


def test_le_letture_non_lasciano_la_connessione_in_transazione_aperta(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)

    repository.registrazioni_da_processare()
    assert connessione.info.transaction_status == psycopg.pq.TransactionStatus.IDLE

    repository.trova_lezione("Analisi 1", date(2026, 3, 5))
    assert connessione.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


def test_una_registrazione_salvata_e_ritrovabile_con_la_sua_lezione(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)

    salva(repository, crea_registrazione("reg-1"))
    trovate = repository.registrazioni_da_processare()

    assert len(trovate) == 1
    assert trovate[0].id == "reg-1"
    assert trovate[0].lezione.materia == "Analisi 1"
    assert trovate[0].lezione.data == date(2026, 3, 5)
    assert trovate[0].lezione.chat_id == "fratello-1"
    assert trovate[0].percorso_audio == "/audio/reg-1.ogg"
    assert trovate[0].stato is Stato.RICEVUTA


def test_una_registrazione_notificata_non_e_tra_quelle_da_processare(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)

    salva(repository, crea_registrazione("reg-2", stato=Stato.NOTIFICATA))

    assert repository.registrazioni_da_processare() == []


def test_il_testo_della_trascrizione_sopravvive_al_salvataggio_e_al_ricaricamento(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)

    salva(
        repository,
        crea_registrazione(
            "reg-3", stato=Stato.TRASCRITTA, trascrizione="questo è il testo trascritto"
        ),
    )
    trovate = repository.registrazioni_da_processare()

    assert len(trovate) == 1
    assert trovate[0].trascrizione == "questo è il testo trascritto"


def test_trova_lezione_ritrova_quella_della_stessa_materia_e_giorno(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    salva(repository, crea_registrazione("reg-5", materia="Fisica 1", data=date(2026, 3, 6)))

    trovata = repository.trova_lezione("Fisica 1", date(2026, 3, 6))

    assert trovata is not None
    assert trovata.id == "lezione-reg-5"
    assert repository.trova_lezione("Fisica 1", date(2026, 3, 7)) is None
    assert repository.trova_lezione("Analisi 1", date(2026, 3, 6)) is None


def test_due_registrazioni_della_stessa_lezione_escono_in_ordine_di_arrivo(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    prima = crea_registrazione("reg-prima", lezione_id="lezione-comune")
    seconda = crea_registrazione("reg-seconda", lezione_id="lezione-comune")

    repository.salva_lezione(prima.lezione)
    repository.salva_registrazione(prima)
    repository.salva_registrazione(seconda)
    trovate = repository.registrazioni_da_processare()

    assert [r.id for r in trovate] == ["reg-prima", "reg-seconda"]
    assert {r.lezione.id for r in trovate} == {"lezione-comune"}


def test_non_possono_esistere_due_lezioni_con_la_stessa_materia_e_giorno(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    repository.salva_lezione(Lezione(id="a", materia="Analisi 1", data=date(2026, 3, 5), chat_id="c"))

    with pytest.raises(psycopg.errors.UniqueViolation):
        repository.salva_lezione(
            Lezione(id="b", materia="Analisi 1", data=date(2026, 3, 5), chat_id="c")
        )


def test_i_capitoli_di_una_registrazione_si_salvano_e_si_rileggono_in_ordine(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea_registrazione("reg-cap-1", stato=Stato.SEGMENTATA)
    salva(repository, registrazione)

    repository.sostituisci_capitoli(
        registrazione, [CapitoloTagliato("Insiemi", "testo uno."), CapitoloTagliato("Funzioni", "testo due.")]
    )
    capitoli = repository.capitoli_della_lezione(registrazione.lezione)

    assert [(c.posizione, c.titolo, c.testo) for c in capitoli] == [
        (0, "Insiemi", "testo uno."),
        (1, "Funzioni", "testo due."),
    ]
    assert {c.registrazione_id for c in capitoli} == {"reg-cap-1"}
    assert repository.registrazioni_da_processare()[0].stato is Stato.SEGMENTATA


def test_rifare_la_segmentazione_sostituisce_i_capitoli_senza_duplicarli(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea_registrazione("reg-cap-2")
    salva(repository, registrazione)

    repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("A", "1"), CapitoloTagliato("B", "2")])
    repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("Unico", "12")])

    capitoli = repository.capitoli_della_lezione(registrazione.lezione)
    assert [(c.posizione, c.titolo) for c in capitoli] == [(0, "Unico")]


def test_i_capitoli_di_una_seconda_registrazione_seguono_quelli_della_prima(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    prima = crea_registrazione("reg-prima", lezione_id="lezione-cap")
    seconda = crea_registrazione("reg-seconda", lezione_id="lezione-cap")
    repository.salva_lezione(prima.lezione)
    repository.salva_registrazione(prima)
    repository.salva_registrazione(seconda)

    # La seconda finisce la segmentazione per prima: l'ordine resta quello di arrivo.
    repository.sostituisci_capitoli(seconda, [CapitoloTagliato("S1", "s1"), CapitoloTagliato("S2", "s2")])
    repository.sostituisci_capitoli(prima, [CapitoloTagliato("P1", "p1")])
    repository.sostituisci_capitoli(prima, [CapitoloTagliato("P1", "p1"), CapitoloTagliato("P2", "p2")])

    capitoli = repository.capitoli_della_lezione(prima.lezione)
    assert [c.titolo for c in capitoli] == ["P1", "P2", "S1", "S2"]


def test_i_capitoli_di_altre_lezioni_non_si_mescolano(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    una = crea_registrazione("reg-una", materia="Analisi 1")
    altra = crea_registrazione("reg-altra", materia="Fisica 1")
    salva(repository, una)
    salva(repository, altra)
    repository.sostituisci_capitoli(una, [CapitoloTagliato("Analisi", "a")])
    repository.sostituisci_capitoli(altra, [CapitoloTagliato("Fisica", "f")])

    assert [c.titolo for c in repository.capitoli_della_lezione(una.lezione)] == ["Analisi"]


def test_una_scrittura_fallita_non_lascia_la_connessione_inutilizzabile(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea_registrazione("reg-rollback")
    salva(repository, registrazione)

    with pytest.raises(psycopg.errors.NotNullViolation):
        repository.sostituisci_capitoli(
            registrazione, [CapitoloTagliato("Valido", "testo"), CapitoloTagliato(None, "x")]  # type: ignore[arg-type]
        )

    # Il DELETE e il primo INSERT sono stati annullati insieme al resto, e la connessione funziona.
    assert repository.capitoli_della_lezione(registrazione.lezione) == []
    repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("Ok", "testo")])
    assert len(repository.capitoli_della_lezione(registrazione.lezione)) == 1


APPUNTI = AppuntiCapitolo(
    riassunto="Si definisce l'insieme.",
    punti_chiave=["Un insieme è una collezione"],
    termini=[Termine("Insieme", "Collezione di elementi.")],
    da_ripassare=["Appartenenza e inclusione"],
    domande=[Domanda("Che cos'è un insieme?", "Una collezione.")],
)


def test_gli_appunti_di_un_capitolo_sopravvivono_al_salvataggio_e_al_ricaricamento(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea_registrazione("reg-app-1")
    salva(repository, registrazione)
    repository.sostituisci_capitoli(
        registrazione, [CapitoloTagliato("Insiemi", "testo"), CapitoloTagliato("Funzioni", "testo 2")]
    )
    primo = repository.capitoli_della_lezione(registrazione.lezione)[0]
    assert primo.appunti is None

    repository.salva_appunti(primo, APPUNTI)
    capitoli = repository.capitoli_della_lezione(registrazione.lezione)

    assert capitoli[0].appunti == APPUNTI
    assert capitoli[1].appunti is None  # gli altri Capitoli non vengono toccati


def test_salvare_appunti_di_un_capitolo_inesistente_solleva_errore(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea_registrazione("reg-app-2")
    salva(repository, registrazione)
    repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("Insiemi", "testo")])
    fantasma = repository.capitoli_della_lezione(registrazione.lezione)[0]
    repository.sostituisci_capitoli(registrazione, [])

    with pytest.raises(LookupError):
        repository.salva_appunti(fantasma, APPUNTI)


def test_rifare_la_segmentazione_elimina_anche_gli_appunti_dei_vecchi_capitoli(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea_registrazione("reg-app-3")
    salva(repository, registrazione)
    repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("Vecchio", "testo")])
    repository.salva_appunti(repository.capitoli_della_lezione(registrazione.lezione)[0], APPUNTI)

    repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("Nuovo", "testo")])

    assert repository.capitoli_della_lezione(registrazione.lezione)[0].appunti is None


def test_il_quadro_generale_si_salva_sulla_lezione_e_si_rilegge(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea_registrazione("reg-quadro-1")
    salva(repository, registrazione)

    repository.salva_quadro_generale(registrazione.lezione, "Una lezione sugli insiemi.")

    rilettura = repository.trova_lezione(registrazione.lezione.materia, registrazione.lezione.data)
    assert rilettura is not None
    assert rilettura.quadro_generale == "Una lezione sugli insiemi."
    da_processare = repository.registrazioni_da_processare()
    assert da_processare[0].lezione.quadro_generale == "Una lezione sugli insiemi."


def test_risalvare_la_lezione_non_cancella_il_quadro_generale(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea_registrazione("reg-quadro-2")
    salva(repository, registrazione)
    repository.salva_quadro_generale(registrazione.lezione, "Quadro.")

    repository.salva_lezione(registrazione.lezione)  # copia con quadro_generale ancora None

    rilettura = repository.trova_lezione(registrazione.lezione.materia, registrazione.lezione.data)
    assert rilettura is not None and rilettura.quadro_generale == "Quadro."


def _lezione_elaborata(repository: RepositoryPostgres, lezione_id: str, *registrazioni: str) -> Lezione:
    lezione = Lezione(lezione_id, "Analisi 1", date(2026, 3, 5), "fratello-1")
    repository.salva_lezione(lezione)
    repository.salva_quadro_generale(lezione, "Un quadro generale.")
    for id_ in registrazioni:
        registrazione = Registrazione(
            id_,
            lezione,
            f"/audio/{id_}.ogg",
            stato=Stato.NOTIFICATA,
            trascrizione=f"trascrizione di {id_}",
            percorso_appunti="/archivio/vecchio.md",
            tentativi=1,
        )
        repository.salva_registrazione(registrazione)
        repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("Titolo", "testo")])
        repository.salva_appunti(
            repository.capitoli_della_lezione(lezione)[-1], AppuntiCapitolo(riassunto="Vecchio.")
        )
    return lezione


def test_riavviare_l_elaborazione_riporta_le_registrazioni_a_trascritta_senza_capitoli(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = _lezione_elaborata(repository, "l1", "r1", "r2")

    riavviate = repository.riavvia_elaborazione(lezione)

    assert riavviate == 2
    da_fare = repository.registrazioni_da_processare()
    assert [(r.id, r.stato, r.tentativi, r.percorso_appunti) for r in da_fare] == [
        ("r1", Stato.TRASCRITTA, 0, None),
        ("r2", Stato.TRASCRITTA, 0, None),
    ]
    assert da_fare[0].trascrizione == "trascrizione di r1"  # la trascrizione si conserva
    assert repository.capitoli_della_lezione(lezione) == []
    riletta = repository.trova_lezione(lezione.materia, lezione.data)
    assert riletta is not None and riletta.quadro_generale is None


def test_riavviare_non_tocca_registrazioni_senza_trascrizione_ne_altre_lezioni(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = _lezione_elaborata(repository, "l1", "r1")
    ricevuta = Registrazione("r-nuova", lezione, "/audio/nuova.ogg")  # ancora da trascrivere
    repository.salva_registrazione(ricevuta)
    altra = Lezione("l2", "Fisica 1", date(2026, 3, 6), "c")
    repository.salva_lezione(altra)
    repository.salva_registrazione(
        Registrazione("r-altra", altra, "/a.ogg", stato=Stato.NOTIFICATA, trascrizione="t")
    )

    assert repository.riavvia_elaborazione(lezione) == 1

    stati = {r.id: r.stato for r in repository.registrazioni_da_processare()}
    assert stati == {"r1": Stato.TRASCRITTA, "r-nuova": Stato.RICEVUTA}  # r-altra resta notificata


def test_riavviare_una_lezione_senza_registrazioni_trascritte_restituisce_zero(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = Lezione("l1", "Analisi 1", date(2026, 3, 5), "c")
    repository.salva_lezione(lezione)

    assert repository.riavvia_elaborazione(lezione) == 0


def test_riavviare_senza_registrazioni_trascritte_non_cancella_il_quadro_generale(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = Lezione("l1", "Analisi 1", date(2026, 3, 5), "c")
    repository.salva_lezione(lezione)
    repository.salva_quadro_generale(lezione, "Quadro da conservare.")

    assert repository.riavvia_elaborazione(lezione) == 0

    riletta = repository.trova_lezione(lezione.materia, lezione.data)
    assert riletta is not None and riletta.quadro_generale == "Quadro da conservare."


def test_non_si_riavvia_una_lezione_con_registrazioni_ancora_in_lavorazione(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = _lezione_elaborata(repository, "l1", "r1")
    in_corso = Registrazione(
        "r2", lezione, "/a.ogg", stato=Stato.SEGMENTATA, trascrizione="testo"
    )
    repository.salva_registrazione(in_corso)

    with pytest.raises(ElaborazioneInCorso, match="r2"):
        repository.riavvia_elaborazione(lezione)

    # Non è cambiato niente.
    assert repository.capitoli_della_lezione(lezione) != []
    assert {r.id: r.stato for r in repository.registrazioni_da_processare()} == {
        "r2": Stato.SEGMENTATA
    }


def test_le_registrazioni_in_errore_si_possono_riavviare(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = Lezione("l1", "Analisi 1", date(2026, 3, 5), "c")
    repository.salva_lezione(lezione)
    repository.salva_registrazione(
        Registrazione("r1", lezione, "/a.ogg", stato=Stato.ERRORE, trascrizione="t", tentativi=2)
    )

    assert repository.riavvia_elaborazione(lezione) == 1


def test_capitoli_con_progresso_conta_quelli_con_uno_stato_diverso_da_da_studiare(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = _lezione_elaborata(repository, "l1", "r1", "r2")
    assert repository.capitoli_con_progresso(lezione) == 0

    with connessione.cursor() as cursore:
        cursore.execute("UPDATE capitoli SET stato_comprensione = 'compreso' WHERE registrazione_id = 'r1'")
    connessione.commit()

    assert repository.capitoli_con_progresso(lezione) == 1


def test_registrazioni_ferme_trova_solo_quelle_in_lavorazione_che_non_cambiano_da_tempo(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    salva(repository, crea_registrazione("ferma", data=date(2026, 3, 5)))
    salva(repository, crea_registrazione("recente", data=date(2026, 3, 6)))
    salva(repository, crea_registrazione("finita", data=date(2026, 3, 7), stato=Stato.NOTIFICATA))
    with connessione.cursor() as cursore:
        cursore.execute(
            "UPDATE registrazioni SET aggiornato_il = now() - interval '13 hours' "
            "WHERE id IN ('ferma', 'finita')"
        )
    connessione.commit()

    ferme = repository.registrazioni_ferme(timedelta(hours=12))

    assert [r.id for r in ferme] == ["ferma"]
    assert connessione.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
