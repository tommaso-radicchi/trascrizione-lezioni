from __future__ import annotations

import pytest

from trascrizione_lezioni.dominio import AppuntiCapitolo, Domanda, Termine

COMPLETI = AppuntiCapitolo(
    riassunto="Riassunto.",
    punti_chiave=["a", "b"],
    termini=[Termine("Insieme", "Collezione.")],
    da_ripassare=["Inclusione"],
    domande=[Domanda("Che cos'è?", "Una collezione.")],
)


def test_gli_appunti_sopravvivono_al_giro_dizionario() -> None:
    assert AppuntiCapitolo.da_dict(COMPLETI.a_dict()) == COMPLETI


def test_le_liste_opzionali_mancanti_o_nulle_diventano_vuote() -> None:
    appunti = AppuntiCapitolo.da_dict({"riassunto": "R.", "punti_chiave": None})

    assert appunti == AppuntiCapitolo(riassunto="R.")


@pytest.mark.parametrize(
    "dati",
    [
        {},
        {"punti_chiave": ["a"]},
        {"riassunto": "R.", "termini": [{"termine": "senza definizione"}]},
        {"riassunto": "R.", "domande": ["solo testo"]},
        {"riassunto": "R.", "punti_chiave": 5},
    ],
)
def test_una_forma_non_valida_solleva_value_error(dati: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="Appunti"):
        AppuntiCapitolo.da_dict(dati)
