from __future__ import annotations

from pathlib import Path

import pytest

from trascrizione_lezioni.config import carica_materie_correnti


def test_carica_materie_correnti_legge_una_lista_da_yaml(tmp_path: Path) -> None:
    percorso = tmp_path / "materie.yaml"
    percorso.write_text("- Analisi 1\n- Fisica 1\n", encoding="utf-8")

    materie = carica_materie_correnti(percorso)

    assert materie == ["Analisi 1", "Fisica 1"]


def test_carica_materie_correnti_rifiuta_un_contenuto_non_a_lista(tmp_path: Path) -> None:
    percorso = tmp_path / "materie.yaml"
    percorso.write_text("materia: Analisi 1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        carica_materie_correnti(percorso)
