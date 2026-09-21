from __future__ import annotations

from datetime import date

from trascrizione_lezioni.dominio import Lezione
from trascrizione_lezioni.notifica import componi_notifica

LEZIONE = Lezione(id="l1", materia="Matematica Generale", data=date(2026, 9, 21), chat_id="c")


def test_la_notifica_dice_materia_data_e_titoli_degli_argomenti_nuovi() -> None:
    testo = componi_notifica(LEZIONE, ["Insiemi", "Funzioni", "Limiti"])

    assert testo == (
        "📚 Appunti aggiornati: Matematica Generale 21/09\n"
        "\n"
        "3 nuovi argomenti:\n"
        "• Insiemi\n"
        "• Funzioni\n"
        "• Limiti"
    )


def test_con_un_solo_argomento_il_testo_e_al_singolare() -> None:
    testo = componi_notifica(LEZIONE, ["Insiemi"])

    assert "1 nuovo argomento:" in testo
    assert "• Insiemi" in testo


def test_senza_titoli_resta_solo_l_intestazione() -> None:
    assert componi_notifica(LEZIONE, []) == "📚 Appunti aggiornati: Matematica Generale 21/09"


def test_la_notifica_non_contiene_gli_appunti_ne_html() -> None:
    testo = componi_notifica(LEZIONE, ["Insiemi"])

    assert "<" not in testo
    assert "Riassunto" not in testo


def test_con_un_link_la_notifica_lo_mette_in_fondo() -> None:
    testo = componi_notifica(LEZIONE, ["Insiemi"], link="https://studio.example/capitolo/r1/0")

    assert testo.endswith("\n\n👉 https://studio.example/capitolo/r1/0")
    assert testo.startswith("📚 Appunti aggiornati: Matematica Generale 21/09")


def test_il_link_c_e_anche_senza_titoli() -> None:
    testo = componi_notifica(LEZIONE, [], link="https://studio.example/x")

    assert testo == "📚 Appunti aggiornati: Matematica Generale 21/09\n\n👉 https://studio.example/x"


def test_senza_link_il_testo_non_cambia() -> None:
    assert componi_notifica(LEZIONE, ["Insiemi"]) == componi_notifica(LEZIONE, ["Insiemi"], link=None)
    assert "👉" not in componi_notifica(LEZIONE, ["Insiemi"])
