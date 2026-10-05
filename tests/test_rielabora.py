from __future__ import annotations

import os
from datetime import date

import psycopg
import pytest

from trascrizione_lezioni.adapters.postgres import RepositoryPostgres
from trascrizione_lezioni.dominio import (
    AppuntiCapitolo,
    CapitoloTagliato,
    Lezione,
    Registrazione,
    Stato,
)
from trascrizione_lezioni.rielabora import main


@pytest.fixture
def lezione_notificata(
    connessione: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> tuple[RepositoryPostgres, Lezione]:
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL_TEST"])
    repository = RepositoryPostgres(connessione)
    lezione = Lezione("l1", "Analisi 1", date(2026, 3, 5), "c")
    repository.salva_lezione(lezione)
    registrazione = Registrazione(
        "r1", lezione, "/a.ogg", stato=Stato.NOTIFICATA, trascrizione="testo trascritto"
    )
    repository.salva_registrazione(registrazione)
    repository.sostituisci_capitoli(registrazione, [CapitoloTagliato("Titolo", "testo")])
    repository.salva_appunti(
        repository.capitoli_della_lezione(lezione)[0], AppuntiCapitolo(riassunto="Vecchio.")
    )
    return repository, lezione


def test_riavvia_la_lezione_e_lo_dice(
    lezione_notificata: tuple[RepositoryPostgres, Lezione], capsys: pytest.CaptureFixture[str]
) -> None:
    repository, lezione = lezione_notificata

    assert main(["Analisi 1", "2026-03-05"]) == 0

    assert "1 Registrazioni riavviate" in capsys.readouterr().out
    assert [r.stato for r in repository.registrazioni_da_processare()] == [Stato.TRASCRITTA]


def test_una_lezione_inesistente_da_errore_senza_toccare_nulla(
    lezione_notificata: tuple[RepositoryPostgres, Lezione], capsys: pytest.CaptureFixture[str]
) -> None:
    repository, _ = lezione_notificata

    assert main(["Fisica 1", "2026-03-05"]) == 1

    assert "Nessuna Lezione" in capsys.readouterr().err
    assert repository.registrazioni_da_processare() == []  # r1 è ancora notificata


def test_si_rifiuta_se_ci_sono_capitoli_con_progresso_di_studio(
    lezione_notificata: tuple[RepositoryPostgres, Lezione],
    connessione: psycopg.Connection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository, lezione = lezione_notificata
    with connessione.cursor() as cursore:
        cursore.execute("UPDATE capitoli SET stato_comprensione = 'compreso'")
    connessione.commit()

    assert main(["Analisi 1", "2026-03-05"]) == 1

    errore = capsys.readouterr().err
    assert "1 Capitoli" in errore and "--forza" in errore
    assert repository.capitoli_della_lezione(lezione) != []  # niente è stato cancellato


def test_con_forza_riavvia_anche_se_c_e_progresso(
    lezione_notificata: tuple[RepositoryPostgres, Lezione], connessione: psycopg.Connection
) -> None:
    repository, lezione = lezione_notificata
    with connessione.cursor() as cursore:
        cursore.execute("UPDATE capitoli SET stato_comprensione = 'compreso'")
    connessione.commit()

    assert main(["Analisi 1", "2026-03-05", "--forza"]) == 0

    assert repository.capitoli_della_lezione(lezione) == []


def test_si_rifiuta_se_l_orchestratore_sta_ancora_lavorando_sulla_lezione(
    lezione_notificata: tuple[RepositoryPostgres, Lezione], capsys: pytest.CaptureFixture[str]
) -> None:
    repository, lezione = lezione_notificata
    repository.salva_registrazione(
        Registrazione("r2", lezione, "/b.ogg", stato=Stato.ELABORATA, trascrizione="testo")
    )

    assert main(["Analisi 1", "2026-03-05"]) == 1

    assert "in lavorazione" in capsys.readouterr().err


def test_senza_argomenti_stampa_l_uso(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2

    assert "Uso:" in capsys.readouterr().err


def test_una_data_non_valida_viene_rifiutata(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["Analisi 1", "5 marzo"]) == 2

    assert "Data non valida" in capsys.readouterr().err
