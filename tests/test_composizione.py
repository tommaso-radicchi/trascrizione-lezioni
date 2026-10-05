from __future__ import annotations

from datetime import date

from trascrizione_lezioni.composizione import componi_markdown
from trascrizione_lezioni.dominio import AppuntiCapitolo, Capitolo, Domanda, Lezione, Termine


def lezione(quadro_generale: str | None = "Introduzione alla teoria degli insiemi.") -> Lezione:
    return Lezione(
        id="l1",
        materia="Matematica Generale",
        data=date(2026, 9, 21),
        chat_id="c",
        quadro_generale=quadro_generale,
    )


def capitolo(
    posizione: int, titolo: str, appunti: AppuntiCapitolo | None, registrazione: str = "r1"
) -> Capitolo:
    return Capitolo(registrazione, posizione, titolo, "testo originale", appunti)


APPUNTI_COMPLETI = AppuntiCapitolo(
    riassunto="Si definisce l'insieme.",
    punti_chiave=["Un insieme è una collezione", "L'insieme vuoto non ha elementi"],
    termini=[Termine("Insieme", "Collezione di elementi.")],
    da_ripassare=["La differenza tra appartenenza e inclusione"],
    domande=[
        Domanda("Che cos'è un insieme?", "Una collezione di elementi."),
        Domanda("Che cos'è l'insieme vuoto?", "Un insieme senza elementi."),
    ],
)


def test_il_documento_ha_titolo_data_quadro_generale_ed_elenco_degli_argomenti() -> None:
    markdown = componi_markdown(
        lezione(),
        [
            capitolo(0, "Insiemi", APPUNTI_COMPLETI),
            capitolo(1, "Funzioni", AppuntiCapitolo(riassunto="Le funzioni.")),
        ],
    )

    assert markdown.startswith("# Matematica Generale\n\n**Data**: 21/09/2026\n")
    assert "## Quadro generale\n\nIntroduzione alla teoria degli insiemi." in markdown
    assert "**Argomenti**\n\n1. Insiemi\n2. Funzioni\n" in markdown


def test_ogni_capitolo_ha_le_sue_sezioni_nell_ordine() -> None:
    markdown = componi_markdown(lezione(), [capitolo(0, "Insiemi", APPUNTI_COMPLETI)])

    ordine = [
        "## 1. Insiemi",
        "### Riassunto\n\nSi definisce l'insieme.",
        "### Punti chiave\n\n- Un insieme è una collezione\n- L'insieme vuoto non ha elementi",
        "### Termini\n\n- **Insieme**: Collezione di elementi.",
        "### Da ripassare\n\n- La differenza tra appartenenza e inclusione",
        "### Domande",
    ]
    posizioni = [markdown.index(pezzo) for pezzo in ordine]
    assert posizioni == sorted(posizioni)


def test_le_risposte_alle_domande_sono_nascoste_in_un_details() -> None:
    markdown = componi_markdown(lezione(), [capitolo(0, "Insiemi", APPUNTI_COMPLETI)])

    assert (
        "**1. Che cos'è un insieme?**\n\n"
        "<details>\n<summary>Risposta</summary>\n\nUna collezione di elementi.\n\n</details>"
    ) in markdown
    assert "**2. Che cos'è l'insieme vuoto?**" in markdown


def test_le_sezioni_vuote_vengono_omesse() -> None:
    markdown = componi_markdown(
        lezione(), [capitolo(0, "Funzioni", AppuntiCapitolo(riassunto="Le funzioni."))]
    )

    assert "### Riassunto" in markdown
    for sezione in ("### Punti chiave", "### Termini", "### Da ripassare", "### Domande"):
        assert sezione not in markdown
    assert "<details>" not in markdown


def test_senza_quadro_generale_la_sezione_non_compare() -> None:
    markdown = componi_markdown(
        lezione(quadro_generale=None), [capitolo(0, "Insiemi", APPUNTI_COMPLETI)]
    )

    assert "## Quadro generale" not in markdown
    assert "**Argomenti**" in markdown


def test_i_capitoli_senza_appunti_non_compaiono_ne_nell_elenco_ne_nel_corpo() -> None:
    markdown = componi_markdown(
        lezione(),
        [
            capitolo(0, "Pronto", APPUNTI_COMPLETI),
            capitolo(1, "Non ancora elaborato", None, registrazione="r2"),
        ],
    )

    assert "Pronto" in markdown
    assert "Non ancora elaborato" not in markdown


def test_i_capitoli_di_piu_registrazioni_sono_numerati_di_seguito() -> None:
    markdown = componi_markdown(
        lezione(),
        [
            capitolo(0, "Primo audio A", APPUNTI_COMPLETI, registrazione="r1"),
            capitolo(1, "Primo audio B", APPUNTI_COMPLETI, registrazione="r1"),
            capitolo(0, "Secondo audio A", APPUNTI_COMPLETI, registrazione="r2"),
        ],
    )

    assert "1. Primo audio A\n2. Primo audio B\n3. Secondo audio A" in markdown
    assert "## 3. Secondo audio A" in markdown


def test_la_composizione_e_deterministica_e_non_include_il_testo_originale() -> None:
    capitoli = [capitolo(0, "Insiemi", APPUNTI_COMPLETI)]

    assert componi_markdown(lezione(), capitoli) == componi_markdown(lezione(), capitoli)
    assert "testo originale" not in componi_markdown(lezione(), capitoli)
