"""Test di contratto per RepositoryPostgres: gira contro un Postgres reale
(docker compose up postgres). Fuori dal seam principale dell'Orchestratore,
per policy dallo spec (vedi issue #1, sezione Testing Decisions)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date

import psycopg
import pytest
from dotenv import load_dotenv

from trascrizione_lezioni.adapters.postgres import RepositoryPostgres
from trascrizione_lezioni.dominio import Lezione, Stato

load_dotenv()


@pytest.fixture
def connessione() -> Iterator[psycopg.Connection]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL non impostata")
    try:
        conn = psycopg.connect(url, connect_timeout=2)
    except psycopg.OperationalError as errore:
        pytest.skip(f"Postgres non raggiungibile: {errore}")
    with conn.cursor() as cursore:
        cursore.execute("TRUNCATE TABLE lezioni")
    conn.commit()
    yield conn
    conn.close()


def test_una_lezione_salvata_e_ritrovabile_tra_quelle_da_processare(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = Lezione(
        id="lezione-contratto-1",
        materia="Analisi 1",
        data=date(2026, 3, 5),
        percorso_audio="/audio/lezione-contratto-1.ogg",
        chat_id="fratello-1",
    )

    repository.salva(lezione)
    trovate = repository.da_processare()

    assert len(trovate) == 1
    assert trovate[0].id == "lezione-contratto-1"
    assert trovate[0].materia == "Analisi 1"
    assert trovate[0].data == date(2026, 3, 5)
    assert trovate[0].stato is Stato.RICEVUTA


def test_una_lezione_notificata_non_e_tra_quelle_da_processare(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = Lezione(
        id="lezione-contratto-2",
        materia="Fisica 1",
        data=date(2026, 3, 6),
        percorso_audio="/audio/lezione-contratto-2.ogg",
        chat_id="fratello-1",
        stato=Stato.NOTIFICATA,
    )

    repository.salva(lezione)
    trovate = repository.da_processare()

    assert trovate == []


def test_il_testo_della_trascrizione_sopravvive_al_salvataggio_e_al_ricaricamento(
    connessione: psycopg.Connection,
) -> None:
    repository = RepositoryPostgres(connessione)
    lezione = Lezione(
        id="lezione-contratto-3",
        materia="Diritto Pubblico",
        data=date(2026, 3, 7),
        percorso_audio="/audio/lezione-contratto-3.ogg",
        chat_id="fratello-1",
        stato=Stato.TRASCRITTA,
        trascrizione="questo è il testo trascritto dalla lezione",
    )

    repository.salva(lezione)
    trovate = repository.da_processare()

    assert len(trovate) == 1
    assert trovate[0].trascrizione == "questo è il testo trascritto dalla lezione"
