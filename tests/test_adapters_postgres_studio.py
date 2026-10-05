"""Test di contratto per LetturaStudioPostgres, contro un Postgres reale
(vedi tests/conftest.py: usa DATABASE_URL_TEST, mai quello di produzione)."""

from __future__ import annotations

from datetime import date

import psycopg

from trascrizione_lezioni.adapters.postgres import RepositoryPostgres
from trascrizione_lezioni.adapters.postgres_studio import LetturaStudioPostgres
from trascrizione_lezioni.dominio import (
    AppuntiCapitolo,
    CapitoloTagliato,
    Lezione,
    Registrazione,
    StatoComprensione,
)

APPUNTI = AppuntiCapitolo(riassunto="Riassunto.", punti_chiave=["a"])


def crea(
    repository: RepositoryPostgres,
    registrazione_id: str,
    *titoli: str,
    lezione: Lezione | None = None,
    con_appunti: bool = True,
) -> Registrazione:
    lezione = lezione or Lezione(
        id=f"lezione-{registrazione_id}", materia="Analisi 1", data=date(2026, 3, 5), chat_id="c"
    )
    registrazione = Registrazione(registrazione_id, lezione, f"/audio/{registrazione_id}.ogg")
    repository.salva_lezione(lezione)
    repository.salva_registrazione(registrazione)
    repository.sostituisci_capitoli(
        registrazione, [CapitoloTagliato(titolo, f"testo di {titolo}") for titolo in titoli]
    )
    if con_appunti:
        for capitolo in repository.capitoli_della_lezione(lezione):
            if capitolo.registrazione_id == registrazione_id:
                repository.salva_appunti(capitolo, APPUNTI)
    return registrazione


def test_le_lezioni_escono_dalla_piu_vecchia_con_i_capitoli_numerati_di_seguito(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    recente = Lezione("l-recente", "Fisica 1", date(2026, 3, 9), "c")
    vecchia = Lezione("l-vecchia", "Analisi 1", date(2026, 3, 2), "c")
    crea(repository, "r-recente", "F1", lezione=recente)
    crea(repository, "r-a", "A1", "A2", lezione=vecchia)
    crea(repository, "r-b", "A3", lezione=vecchia)  # secondo audio della stessa Lezione

    lezioni = LetturaStudioPostgres(connessione).lezioni()

    assert [l.id for l in lezioni] == ["l-vecchia", "l-recente"]
    assert [(c.numero, c.titolo, c.registrazione_id) for c in lezioni[0].capitoli] == [
        (1, "A1", "r-a"),
        (2, "A2", "r-a"),
        (3, "A3", "r-b"),
    ]
    assert all(c.stato is StatoComprensione.DA_STUDIARE for c in lezioni[0].capitoli)


def test_i_capitoli_senza_appunti_e_le_lezioni_senza_capitoli_elaborati_non_compaiono(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = Lezione("l1", "Analisi 1", date(2026, 3, 5), "c")
    crea(repository, "r1", "Pronto", lezione=lezione)
    crea(repository, "r2", "Non ancora", lezione=lezione, con_appunti=False)
    crea(repository, "r3", "Solo segmentata", lezione=Lezione("l2", "Fisica 1", date(2026, 3, 6), "c"), con_appunti=False)

    lezioni = LetturaStudioPostgres(connessione).lezioni()

    assert [l.id for l in lezioni] == ["l1"]
    assert [c.titolo for c in lezioni[0].capitoli] == ["Pronto"]


def test_il_dettaglio_ha_testo_appunti_e_la_lezione_con_i_suoi_capitoli(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    crea(repository, "r1", "Insiemi", "Funzioni")

    dettaglio = LetturaStudioPostgres(connessione).dettaglio_capitolo("r1", 1)

    assert dettaglio is not None
    assert dettaglio.capitolo.titolo == "Funzioni"
    assert dettaglio.capitolo.numero == 2
    assert dettaglio.testo == "testo di Funzioni"
    assert dettaglio.appunti == APPUNTI
    assert [c.titolo for c in dettaglio.lezione.capitoli] == ["Insiemi", "Funzioni"]


def test_il_dettaglio_di_un_capitolo_inesistente_o_senza_appunti_e_nessuno(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    crea(repository, "r1", "Senza appunti", con_appunti=False)
    lettura = LetturaStudioPostgres(connessione)

    assert lettura.dettaglio_capitolo("r1", 0) is None
    assert lettura.dettaglio_capitolo("inesistente", 0) is None


def test_lo_stato_si_salva_e_si_rilegge(connessione: psycopg.Connection) -> None:
    repository = RepositoryPostgres(connessione)
    crea(repository, "r1", "Insiemi", "Funzioni")
    lettura = LetturaStudioPostgres(connessione)

    assert lettura.imposta_stato("r1", 1, StatoComprensione.DA_RIPASSARE) is True

    capitoli = lettura.lezioni()[0].capitoli
    assert [c.stato for c in capitoli] == [
        StatoComprensione.DA_STUDIARE,
        StatoComprensione.DA_RIPASSARE,
    ]


def test_impostare_lo_stato_di_un_capitolo_inesistente_restituisce_false(
    connessione: psycopg.Connection,
) -> None:
    assert (
        LetturaStudioPostgres(connessione).imposta_stato("nessuna", 0, StatoComprensione.COMPRESO)
        is False
    )


def test_le_letture_non_lasciano_la_connessione_in_transazione_aperta(
    connessione: psycopg.Connection,
) -> None:
    lettura = LetturaStudioPostgres(connessione)

    lettura.lezioni()
    assert connessione.info.transaction_status == psycopg.pq.TransactionStatus.IDLE

    lettura.dettaglio_capitolo("r", 0)
    assert connessione.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


def test_non_si_puo_impostare_lo_stato_di_un_capitolo_non_ancora_visibile(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    crea(repository, "r1", "Senza appunti", con_appunti=False)
    lettura = LetturaStudioPostgres(connessione)

    assert lettura.imposta_stato("r1", 0, StatoComprensione.COMPRESO) is False


def test_il_dettaglio_riguarda_solo_la_lezione_del_capitolo(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    crea(repository, "r-a", "A1", "A2", lezione=Lezione("l-a", "Analisi 1", date(2026, 3, 2), "c"))
    crea(repository, "r-f", "F1", lezione=Lezione("l-f", "Fisica 1", date(2026, 3, 3), "c"))

    dettaglio = LetturaStudioPostgres(connessione).dettaglio_capitolo("r-f", 0)

    assert dettaglio is not None
    assert dettaglio.lezione.id == "l-f"
    assert [c.titolo for c in dettaglio.lezione.capitoli] == ["F1"]


def test_un_capitolo_e_nuovo_finche_non_viene_aperto(connessione: psycopg.Connection) -> None:
    repository = RepositoryPostgres(connessione)
    crea(repository, "r1", "Insiemi", "Funzioni")
    lettura = LetturaStudioPostgres(connessione)
    assert [c.nuovo for c in lettura.lezioni()[0].capitoli] == [True, True]

    lettura.segna_aperto("r1", 0)

    assert [c.nuovo for c in lettura.lezioni()[0].capitoli] == [False, True]
    dettaglio = lettura.dettaglio_capitolo("r1", 0)
    assert dettaglio is not None and dettaglio.capitolo.nuovo is False


def test_aprire_di_nuovo_un_capitolo_non_cambia_nulla_e_uno_inesistente_non_da_errore(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    crea(repository, "r1", "Insiemi")
    lettura = LetturaStudioPostgres(connessione)

    lettura.segna_aperto("r1", 0)
    lettura.segna_aperto("r1", 0)
    lettura.segna_aperto("nessuna", 9)

    assert [c.nuovo for c in lettura.lezioni()[0].capitoli] == [False]


def test_un_capitolo_rielaborato_torna_nuovo(connessione: psycopg.Connection) -> None:
    repository = RepositoryPostgres(connessione)
    registrazione = crea(repository, "r1", "Insiemi")
    lettura = LetturaStudioPostgres(connessione)
    lettura.segna_aperto("r1", 0)

    repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("Insiemi", "testo")])
    repository.salva_appunti(repository.capitoli_della_lezione(registrazione.lezione)[0], APPUNTI)

    assert lettura.lezioni()[0].capitoli[0].nuovo is True


def test_gli_appunti_della_materia_raccolgono_i_capitoli_di_piu_lezioni_dal_piu_vecchio(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    crea(repository, "r-b", "B1", lezione=Lezione("l-b", "Analisi 1", date(2026, 3, 9), "c"))
    crea(repository, "r-a", "A1", "A2", lezione=Lezione("l-a", "Analisi 1", date(2026, 3, 2), "c"))
    crea(repository, "r-f", "F1", lezione=Lezione("l-f", "Fisica 1", date(2026, 3, 5), "c"))
    crea(repository, "r-n", "Nessun appunto", lezione=Lezione("l-n", "Analisi 1", date(2026, 3, 12), "c"), con_appunti=False)

    voci = LetturaStudioPostgres(connessione).appunti_della_materia("Analisi 1")

    assert [(v.data, v.capitolo.titolo) for v in voci] == [
        (date(2026, 3, 2), "A1"),
        (date(2026, 3, 2), "A2"),
        (date(2026, 3, 9), "B1"),
    ]
    assert voci[0].appunti == APPUNTI
    assert LetturaStudioPostgres(connessione).appunti_della_materia("Storia") == []
