from __future__ import annotations

from datetime import date

from trascrizione_lezioni.dominio import StatoComprensione as S
from trascrizione_lezioni.studio import (
    CapitoloStudio,
    LezioneStudio,
    barra_segmentata,
    colore_materia,
    da_ripassare,
    riepilogo_materie,
)


def cap(numero: int, titolo: str, stato: S = S.DA_STUDIARE, reg: str = "r1") -> CapitoloStudio:
    return CapitoloStudio(reg, numero - 1, titolo, stato, numero)


def lez(materia: str, giorno: int, *capitoli: CapitoloStudio) -> LezioneStudio:
    return LezioneStudio(
        id=f"{materia}-{giorno}",
        materia=materia,
        data=date(2026, 9, giorno),
        quadro_generale=None,
        capitoli=list(capitoli),
    )


def test_il_riepilogo_conta_i_capitoli_per_stato_di_ogni_materia() -> None:
    lezioni = [
        lez("Analisi", 1, cap(1, "a", S.COMPRESO), cap(2, "b", S.IN_CORSO)),
        lez("Analisi", 2, cap(1, "c", S.DA_RIPASSARE), cap(2, "d")),
        lez("Fisica", 3, cap(1, "e", S.COMPRESO)),
    ]

    analisi, fisica = riepilogo_materie(lezioni, ["Analisi", "Fisica"])

    assert analisi.materia == "Analisi"
    assert analisi.contatori == {
        S.COMPRESO: 1,
        S.IN_CORSO: 1,
        S.DA_RIPASSARE: 1,
        S.DA_STUDIARE: 1,
    }
    assert analisi.totale == 4
    assert analisi.ultima_lezione == date(2026, 9, 2)
    assert fisica.contatori[S.COMPRESO] == 1 and fisica.totale == 1


def test_continua_porta_al_primo_capitolo_non_compreso_in_ordine_cronologico() -> None:
    lezioni = [
        lez("Analisi", 5, cap(1, "recente", S.DA_STUDIARE)),
        lez("Analisi", 1, cap(1, "vecchio compreso", S.COMPRESO), cap(2, "vecchio aperto", S.IN_CORSO)),
    ]

    (analisi,) = riepilogo_materie(lezioni, ["Analisi"])

    assert analisi.continua is not None
    assert analisi.continua.titolo == "vecchio aperto"


def test_continua_e_vuoto_se_tutto_e_compreso() -> None:
    (analisi,) = riepilogo_materie([lez("Analisi", 1, cap(1, "a", S.COMPRESO))], ["Analisi"])

    assert analisi.continua is None


def test_un_capitolo_da_ripassare_conta_come_non_compreso_per_continua() -> None:
    (analisi,) = riepilogo_materie(
        [lez("Analisi", 1, cap(1, "a", S.COMPRESO), cap(2, "b", S.DA_RIPASSARE))], ["Analisi"]
    )

    assert analisi.continua is not None and analisi.continua.titolo == "b"


def test_le_materie_correnti_compaiono_anche_senza_lezioni_nell_ordine_del_file() -> None:
    lezioni = [lez("Fisica", 1, cap(1, "a"))]

    riepiloghi = riepilogo_materie(lezioni, ["Analisi", "Fisica", "Diritto"])

    assert [r.materia for r in riepiloghi] == ["Analisi", "Fisica", "Diritto"]
    assert riepiloghi[0].totale == 0 and riepiloghi[0].ultima_lezione is None
    assert riepiloghi[0].continua is None


def test_le_materie_non_correnti_ma_con_lezioni_seguono_in_ordine_alfabetico() -> None:
    lezioni = [lez("Storia", 1, cap(1, "a")), lez("Chimica", 1, cap(1, "b"))]

    riepiloghi = riepilogo_materie(lezioni, ["Analisi"])

    assert [r.materia for r in riepiloghi] == ["Analisi", "Chimica", "Storia"]


def test_da_ripassare_raccoglie_i_capitoli_di_tutte_le_materie_dal_piu_vecchio() -> None:
    lezioni = [
        lez("Fisica", 9, cap(1, "f2", S.DA_RIPASSARE)),
        lez("Analisi", 1, cap(1, "a1", S.DA_RIPASSARE), cap(2, "a2", S.COMPRESO)),
        lez("Analisi", 4, cap(1, "a3", S.IN_CORSO), cap(2, "a4", S.DA_RIPASSARE)),
    ]

    voci = da_ripassare(lezioni)

    assert [(v.materia, v.capitolo.titolo) for v in voci] == [
        ("Analisi", "a1"),
        ("Analisi", "a4"),
        ("Fisica", "f2"),
    ]
    assert voci[0].data == date(2026, 9, 1)


def test_la_barra_segmentata_e_proporzionale_e_senza_totale_finto() -> None:
    contatori = {S.COMPRESO: 6, S.IN_CORSO: 2, S.DA_RIPASSARE: 0, S.DA_STUDIARE: 2}

    segmenti = barra_segmentata(contatori)

    assert [(s.stato, s.percentuale) for s in segmenti] == [
        (S.COMPRESO, 60.0),
        (S.IN_CORSO, 20.0),
        (S.DA_STUDIARE, 20.0),
    ]  # ordine fisso, gli stati a zero non compaiono


def test_la_barra_e_vuota_senza_capitoli() -> None:
    assert barra_segmentata({s: 0 for s in S}) == []


def test_le_materie_correnti_hanno_tinte_diverse_e_stabili() -> None:
    materie = ["Matematica", "Economia", "Diritto", "Fisica"]

    tinte = [colore_materia(m, materie) for m in materie]

    assert len(set(tinte)) == len(materie)
    assert tinte == [colore_materia(m, materie) for m in materie]
    assert all(0 <= t < 360 for t in tinte)


def test_una_materia_non_corrente_ha_comunque_una_tinta_stabile() -> None:
    assert colore_materia("Storia", ["Analisi"]) == colore_materia("Storia", ["Analisi"])
    assert colore_materia("Storia") == colore_materia("Storia", ["Analisi", "Fisica"])
