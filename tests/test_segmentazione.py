from __future__ import annotations

import pytest

from trascrizione_lezioni.dominio import PropostaCapitolo
from trascrizione_lezioni.segmentazione import (
    SegmentazioneNonValida,
    segmenta,
    taglia,
)

from trascrizione_lezioni.adapters.fake import ClientSegmentazioneFake


def parole(prefisso: str, quante: int) -> str:
    return " ".join(f"{prefisso}{i}" for i in range(quante)) + "."


TESTO = f"{parole('alfa', 6)} {parole('beta', 6)} {parole('gamma', 6)}"


def test_taglia_divide_nei_punti_indicati_e_conserva_il_testo_originale() -> None:
    capitoli = taglia(
        TESTO,
        [
            PropostaCapitolo("Primo", "alfa0 alfa1"),
            PropostaCapitolo("Secondo", "beta0 beta1"),
            PropostaCapitolo("Terzo", "gamma0 gamma1"),
        ],
        parole_min=1,
        parole_max=100,
    )

    assert [c.titolo for c in capitoli] == ["Primo", "Secondo", "Terzo"]
    assert capitoli[1].testo.startswith("beta0 beta1")
    assert "".join(c.testo for c in capitoli) == TESTO


def test_il_primo_capitolo_parte_sempre_dall_inizio_anche_col_testo_iniziale_non_indicato() -> None:
    testo = f"Buongiorno a tutti. {parole('alfa', 6)} {parole('beta', 6)}"

    capitoli = taglia(
        testo,
        [PropostaCapitolo("Primo", "alfa0 alfa1"), PropostaCapitolo("Secondo", "beta0 beta1")],
        parole_min=1,
        parole_max=100,
    )

    assert capitoli[0].testo.startswith("Buongiorno a tutti.")
    assert "".join(c.testo for c in capitoli) == testo


def test_la_frase_di_inizio_tollera_maiuscole_punteggiatura_e_spazi() -> None:
    testo = f"{parole('alfa', 6)} Oggi, parliamo di   insiemi: {parole('beta', 6)}"

    capitoli = taglia(
        testo,
        [PropostaCapitolo("Primo", "alfa0 alfa1"), PropostaCapitolo("Insiemi", "oggi parliamo di insiemi")],
        parole_min=1,
        parole_max=100,
    )

    assert capitoli[1].testo.startswith("Oggi, parliamo di   insiemi")
    assert "".join(c.testo for c in capitoli) == testo


def test_una_frase_di_inizio_che_non_si_trova_nel_testo_e_una_segmentazione_non_valida() -> None:
    with pytest.raises(SegmentazioneNonValida, match="non trovata"):
        taglia(
            TESTO,
            [PropostaCapitolo("Primo", "alfa0 alfa1"), PropostaCapitolo("Inventato", "parole mai dette")],
            parole_min=1,
            parole_max=100,
        )


@pytest.mark.parametrize(
    "proposte",
    [
        [],
        [PropostaCapitolo("", "alfa0 alfa1")],
        [PropostaCapitolo("Primo", "alfa0 alfa1"), PropostaCapitolo("Secondo", "")],
    ],
)
def test_proposte_vuote_o_senza_titolo_o_senza_frase_sono_non_valide(
    proposte: list[PropostaCapitolo],
) -> None:
    with pytest.raises(SegmentazioneNonValida):
        taglia(TESTO, proposte, parole_min=1, parole_max=100)


def test_una_frase_gia_usata_non_puo_indicare_un_secondo_capitolo_nello_stesso_punto() -> None:
    with pytest.raises(SegmentazioneNonValida):
        taglia(
            TESTO,
            [PropostaCapitolo("Primo", "alfa0 alfa1"), PropostaCapitolo("Doppio", "alfa0 alfa1")],
            parole_min=1,
            parole_max=100,
        )


def test_i_capitoli_troppo_corti_si_uniscono_tenendo_il_titolo_del_piu_lungo() -> None:
    testo = f"{parole('alfa', 20)} {parole('beta', 3)} {parole('gamma', 20)}"

    capitoli = taglia(
        testo,
        [
            PropostaCapitolo("Lungo A", "alfa0 alfa1"),
            PropostaCapitolo("Corto", "beta0 beta1"),
            PropostaCapitolo("Lungo B", "gamma0 gamma1"),
        ],
        parole_min=10,
        parole_max=100,
    )

    assert len(capitoli) == 2
    assert "".join(c.testo for c in capitoli) == testo
    assert [c.titolo for c in capitoli] == ["Lungo A", "Lungo B"]


def test_un_capitolo_iniziale_troppo_corto_si_unisce_al_successivo() -> None:
    testo = f"{parole('alfa', 3)} {parole('beta', 20)}"

    capitoli = taglia(
        testo,
        [PropostaCapitolo("Corto", "alfa0 alfa1"), PropostaCapitolo("Lungo", "beta0 beta1")],
        parole_min=10,
        parole_max=100,
    )

    assert len(capitoli) == 1
    assert capitoli[0].titolo == "Lungo"
    assert capitoli[0].testo == testo


def test_un_capitolo_troppo_lungo_si_spezza_a_fine_frase_e_numera_i_titoli() -> None:
    frasi = [parole(f"f{n}_", 10) for n in range(10)]  # 10 frasi da 10 parole
    testo = " ".join(frasi)

    capitoli = taglia(
        testo,
        [PropostaCapitolo("Argomento", "f0_0 f0_1")],
        parole_min=1,
        parole_max=40,
    )

    assert len(capitoli) == 3
    assert [c.titolo for c in capitoli] == [
        "Argomento (1/3)",
        "Argomento (2/3)",
        "Argomento (3/3)",
    ]
    assert "".join(c.testo for c in capitoli) == testo
    assert all(c.testo.rstrip().endswith(".") for c in capitoli)
    assert all(len(c.testo.split()) <= 50 for c in capitoli)


def test_una_trascrizione_breve_resta_un_solo_capitolo_anche_sotto_il_minimo() -> None:
    capitoli = taglia(
        "Poche parole.",
        [PropostaCapitolo("Unico", "poche parole")],
        parole_min=1200,
        parole_max=3000,
    )

    assert [c.testo for c in capitoli] == ["Poche parole."]


def test_segmenta_ritenta_una_volta_se_la_prima_risposta_non_e_valida() -> None:
    risposte = [
        [PropostaCapitolo("Primo", "alfa0 alfa1"), PropostaCapitolo("Sbagliato", "parole mai dette")],
        [PropostaCapitolo("Primo", "alfa0 alfa1"), PropostaCapitolo("Secondo", "beta0 beta1")],
    ]
    client = ClientSegmentazioneFake(lambda _: risposte.pop(0))

    risultato = segmenta(TESTO, client, parole_min=1, parole_max=100)

    assert client.chiamate == [TESTO, TESTO]
    assert risultato.motivo_ripiego is None
    assert [c.titolo for c in risultato.capitoli] == ["Primo", "Secondo"]


def test_segmenta_dopo_due_risposte_non_valide_ripiega_su_un_capitolo_generico() -> None:
    client = ClientSegmentazioneFake(lambda _: [PropostaCapitolo("A", "alfa0 alfa1"), PropostaCapitolo("X", "parole mai dette")])

    risultato = segmenta(TESTO, client, parole_min=1, parole_max=100)

    assert len(client.chiamate) == 2
    assert risultato.motivo_ripiego is not None
    assert "non trovata" in risultato.motivo_ripiego
    assert [c.testo for c in risultato.capitoli] == [TESTO]


def test_il_ripiego_su_una_trascrizione_lunga_viene_comunque_spezzato() -> None:
    testo = " ".join(parole(f"f{n}_", 10) for n in range(10))
    client = ClientSegmentazioneFake(lambda _: [])

    risultato = segmenta(testo, client, parole_min=1, parole_max=40)

    assert risultato.motivo_ripiego is not None
    assert len(risultato.capitoli) == 3
    assert "".join(c.testo for c in risultato.capitoli) == testo


def test_segmenta_non_maschera_gli_errori_di_trasporto_col_ripiego() -> None:
    def errore_di_rete(_: str) -> list[PropostaCapitolo]:
        raise ConnectionError("Ollama irraggiungibile")

    client = ClientSegmentazioneFake(errore_di_rete)

    with pytest.raises(ConnectionError):
        segmenta(TESTO, client, parole_min=1, parole_max=100)
