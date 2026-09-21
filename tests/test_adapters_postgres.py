"""Test di contratto per RepositoryPostgres: gira contro un Postgres reale
(docker compose up postgres). Fuori dal seam principale dell'Orchestratore,
per policy dallo spec (vedi issue #1, sezione Testing Decisions).

Usa DATABASE_URL_TEST, mai DATABASE_URL: ogni test svuota le tabelle `lezioni` e `registrazioni`,
quindi deve puntare a un database dedicato (il cui nome finisce in `_test`)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date

import psycopg
import pytest
from dotenv import load_dotenv

from trascrizione_lezioni.adapters.postgres import RepositoryPostgres
from trascrizione_lezioni.dominio import Lezione, Registrazione, Stato

load_dotenv()


@pytest.fixture
def connessione() -> Iterator[psycopg.Connection]:
    url = os.environ.get("DATABASE_URL_TEST")
    if not url:
        pytest.skip("DATABASE_URL_TEST non impostata")
    try:
        conn = psycopg.connect(url, connect_timeout=2)
    except psycopg.OperationalError as errore:
        pytest.skip(f"Postgres non raggiungibile: {errore}")
    with conn.cursor() as cursore:
        cursore.execute("SELECT current_database()")
        nome_database = cursore.fetchone()[0]  # type: ignore[index]
        if url == os.environ.get("DATABASE_URL") or not nome_database.endswith("_test"):
            conn.close()
            pytest.fail(
                f"DATABASE_URL_TEST punta a '{nome_database}': rifiuto di svuotarlo. "
                "Serve un database dedicato il cui nome finisce in '_test'."
            )
        cursore.execute("TRUNCATE TABLE lezioni CASCADE")
    conn.commit()
    yield conn
    conn.close()


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


def test_il_markdown_degli_appunti_sopravvive_al_salvataggio_e_al_ricaricamento(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)

    salva(
        repository,
        crea_registrazione(
            "reg-4",
            stato=Stato.ELABORATA,
            trascrizione="testo trascritto",
            appunti_markdown="# Economia Aziendale\n\n## Riassunto\n...",
        ),
    )
    trovate = repository.registrazioni_da_processare()

    assert len(trovate) == 1
    assert trovate[0].appunti_markdown == "# Economia Aziendale\n\n## Riassunto\n..."


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
