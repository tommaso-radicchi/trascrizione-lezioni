from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from fastapi.testclient import TestClient

from trascrizione_lezioni.adapters.fake import LetturaStudioFake
from trascrizione_lezioni.dominio import AppuntiCapitolo, Domanda, StatoComprensione as S, Termine
from trascrizione_lezioni.studio import CapitoloStudio, LezioneStudio
from trascrizione_lezioni.web.app import crea_app


def cap(reg: str, posizione: int, titolo: str, stato: S = S.DA_STUDIARE) -> CapitoloStudio:
    return CapitoloStudio(reg, posizione, titolo, stato, posizione + 1)


def crea_client(
    lezioni: list[LezioneStudio] | None = None,
    materie: list[str] | None = None,
    dettagli: dict[tuple[str, int], tuple[str, AppuntiCapitolo]] | None = None,
) -> tuple[TestClient, LetturaStudioFake]:
    if lezioni is None:
        lezioni = [
            LezioneStudio(
                "l1", "Analisi", date(2026, 9, 1), "Introduzione agli insiemi.",
                [cap("r1", 0, "Insiemi", S.COMPRESO), cap("r1", 1, "Funzioni", S.DA_RIPASSARE)],
            ),
            LezioneStudio("l2", "Analisi", date(2026, 9, 8), None, [cap("r2", 0, "Limiti")]),
            LezioneStudio("l3", "Fisica", date(2026, 9, 3), None, [cap("r3", 0, "Attrito", S.IN_CORSO)]),
        ]
    lettura = LetturaStudioFake(lezioni, dettagli)

    @contextmanager
    def apri() -> Iterator[LetturaStudioFake]:
        yield lettura

    app = crea_app(apri, materie if materie is not None else ["Analisi", "Fisica"])
    return TestClient(app), lettura


APPUNTI_FUNZIONI = AppuntiCapitolo(
    riassunto="Una funzione associa elementi.",
    punti_chiave=["Dominio e codominio", "Iniettività"],
    termini=[Termine("Dominio", "L'insieme di partenza.")],
    da_ripassare=["Differenza tra iniettiva e suriettiva"],
    domande=[Domanda("Che cos'è una funzione?", "Un'associazione tra insiemi.")],
)


# ---------- dashboard ----------


def test_la_dashboard_mostra_una_scheda_per_materia_con_i_contatori() -> None:
    client, _ = crea_client()

    risposta = client.get("/")

    assert risposta.status_code == 200
    html = risposta.text
    assert 'href="/materia/Analisi"' in html and 'href="/materia/Fisica"' in html
    assert "1 compreso" in html or "1 compresi" in html
    assert "Da ripassare" in html


def test_la_dashboard_elenca_in_cima_i_capitoli_da_ripassare_di_tutte_le_materie() -> None:
    client, _ = crea_client()

    html = client.get("/").text

    sezione = html[html.index('id="da-ripassare"') : html.index('id="materie"')]
    assert 'href="/capitolo/r1/1"' in sezione
    assert "Funzioni" in sezione and "Analisi" in sezione
    assert "Insiemi" not in sezione and "Attrito" not in sezione


def test_continua_porta_al_primo_capitolo_non_compreso_di_ogni_materia() -> None:
    client, _ = crea_client()

    html = client.get("/").text

    scheda_analisi = html[html.index('data-materia="Analisi"') :]
    scheda_analisi = scheda_analisi[: scheda_analisi.index("</article>")]
    assert 'href="/capitolo/r1/1"' in scheda_analisi  # Funzioni: da ripassare, viene prima di Limiti
    scheda_fisica = html[html.index('data-materia="Fisica"') :]
    scheda_fisica = scheda_fisica[: scheda_fisica.index("</article>")]
    assert 'href="/capitolo/r3/0"' in scheda_fisica


def test_una_materia_corrente_senza_lezioni_ha_comunque_la_sua_scheda() -> None:
    client, _ = crea_client(lezioni=[], materie=["Analisi"])

    html = client.get("/").text

    assert 'data-materia="Analisi"' in html
    assert "Nessuna lezione" in html


def test_senza_capitoli_da_ripassare_la_sezione_non_compare() -> None:
    client, _ = crea_client(
        lezioni=[LezioneStudio("l", "Analisi", date(2026, 9, 1), None, [cap("r", 0, "A")])]
    )

    assert 'id="da-ripassare"' not in client.get("/").text


def test_i_titoli_generati_dal_modello_vengono_escapati() -> None:
    client, _ = crea_client(
        lezioni=[
            LezioneStudio(
                "l", "Analisi", date(2026, 9, 1), None,
                [cap("r", 0, "<script>alert(1)</script>", S.DA_RIPASSARE)],
            )
        ]
    )

    html = client.get("/").text

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------- hub della materia ----------


def test_l_hub_della_materia_elenca_le_lezioni_dalla_piu_recente_con_i_capitoli() -> None:
    client, _ = crea_client()

    risposta = client.get("/materia/Analisi")

    assert risposta.status_code == 200
    html = risposta.text
    assert html.index("08/09/2026") < html.index("01/09/2026")
    for titolo in ("Insiemi", "Funzioni", "Limiti"):
        assert titolo in html
    assert 'href="/capitolo/r1/0"' in html
    assert "Attrito" not in html  # un'altra Materia
    assert "Introduzione agli insiemi." in html  # quadro generale


def test_i_capitoli_dell_hub_mostrano_lo_stato_con_testo_e_non_solo_col_colore() -> None:
    client, _ = crea_client()

    html = client.get("/materia/Analisi").text

    assert "Compreso" in html and "Da ripassare" in html and "Da studiare" in html


def test_una_materia_sconosciuta_senza_lezioni_da_404() -> None:
    client, _ = crea_client()

    assert client.get("/materia/Astrologia").status_code == 404


def test_i_nomi_di_materia_con_spazi_funzionano_nei_link() -> None:
    client, _ = crea_client(
        lezioni=[
            LezioneStudio("l", "Matematica Generale", date(2026, 9, 1), None, [cap("r", 0, "A")])
        ],
        materie=["Matematica Generale"],
    )

    assert 'href="/materia/Matematica%20Generale"' in client.get("/").text
    assert client.get("/materia/Matematica%20Generale").status_code == 200


# ---------- lettura del capitolo ----------


def test_il_capitolo_mostra_titolo_appunti_e_domande_con_risposta_nascosta() -> None:
    client, _ = crea_client(
        dettagli={("r1", 1): ("Il testo originale della lezione sulle funzioni.", APPUNTI_FUNZIONI)}
    )

    risposta = client.get("/capitolo/r1/1")

    assert risposta.status_code == 200
    html = risposta.text
    assert "<h1" in html and "Funzioni" in html
    assert "Una funzione associa elementi." in html
    assert "Dominio e codominio" in html
    assert "<strong>Dominio</strong>" in html and "L&#39;insieme di partenza." in html
    assert "Differenza tra iniettiva e suriettiva" in html
    assert "<details" in html and "Che cos&#39;è una funzione?" in html
    assert "Un&#39;associazione tra insiemi." in html


def test_il_capitolo_ha_la_trascrizione_originale_in_un_pannello_separato() -> None:
    client, _ = crea_client(
        dettagli={("r1", 1): ("Il testo originale della lezione sulle funzioni.", APPUNTI_FUNZIONI)}
    )

    html = client.get("/capitolo/r1/1").text

    assert 'id="v-appunti"' in html and 'id="v-trascrizione"' in html
    pannello = html[html.index('class="pannello-trascrizione"') :]
    assert "Il testo originale della lezione sulle funzioni." in pannello


def test_le_sezioni_vuote_degli_appunti_non_compaiono() -> None:
    client, _ = crea_client(
        dettagli={("r1", 0): ("testo", AppuntiCapitolo(riassunto="Solo riassunto."))}
    )

    html = client.get("/capitolo/r1/0").text

    assert "Solo riassunto." in html
    for sezione in ("Punti chiave", "Termini", "Da ripassare</h2>", "Domande"):
        assert sezione not in html


def test_la_linea_del_tempo_mostra_i_capitoli_della_lezione_col_corrente_evidenziato() -> None:
    client, _ = crea_client()

    html = client.get("/capitolo/r1/1").text

    timeline = html[html.index('id="timeline"') : html.index("</nav>", html.index('id="timeline"'))]
    assert 'href="/capitolo/r1/0"' in timeline
    assert 'aria-current="page"' in timeline
    assert timeline.count('aria-current="page"') == 1


def test_precedente_e_successivo_sono_dentro_la_lezione() -> None:
    client, _ = crea_client()

    primo = client.get("/capitolo/r1/0").text
    ultimo = client.get("/capitolo/r1/1").text

    assert 'rel="next" href="/capitolo/r1/1"' in primo
    assert 'rel="prev"' not in primo  # il primo capitolo non ha un precedente
    assert 'rel="prev" href="/capitolo/r1/0"' in ultimo
    assert 'rel="next"' not in ultimo
    assert "Torna a Analisi" in ultimo  # a fine lezione si torna alla Materia


def test_un_capitolo_inesistente_da_404() -> None:
    client, _ = crea_client()

    assert client.get("/capitolo/nessuna/0").status_code == 404


# ---------- stato di comprensione ----------


def test_cambiare_lo_stato_senza_javascript_torna_al_capitolo_e_la_dashboard_si_aggiorna() -> None:
    client, _ = crea_client()
    assert 'href="/capitolo/r3/0"' in client.get("/").text  # Fisica: Attrito ancora in corso

    risposta = client.post("/capitolo/r3/0/stato/compreso", follow_redirects=False)

    assert risposta.status_code == 303
    assert risposta.headers["location"] == "/capitolo/r3/0"
    scheda = client.get("/").text
    scheda = scheda[scheda.index('data-materia="Fisica"') :]
    scheda = scheda[: scheda.index("</article>")]
    assert 'href="/capitolo/r3/0"' not in scheda  # tutto compreso: niente Continua


def test_con_htmx_torna_solo_il_selettore_aggiornato_e_la_linea_del_tempo() -> None:
    client, lettura = crea_client()

    risposta = client.post(
        "/capitolo/r1/0/stato/in_corso", headers={"HX-Request": "true"}
    )

    assert risposta.status_code == 200
    html = risposta.text
    assert 'id="stato-selettore"' in html
    assert 'aria-pressed="true"' in html
    assert 'id="timeline"' in html and 'hx-swap-oob="true"' in html
    assert "<html" not in html  # è un frammento, non una pagina
    assert lettura.lezioni()[0].capitoli[0].stato is S.IN_CORSO


def test_uno_stato_non_valido_o_un_capitolo_inesistente_non_cambia_nulla() -> None:
    client, lettura = crea_client()

    assert client.post("/capitolo/r1/0/stato/finito").status_code == 404
    assert client.post("/capitolo/nessuna/0/stato/compreso").status_code == 404
    assert lettura.lezioni()[0].capitoli[0].stato is S.COMPRESO


def test_il_selettore_evidenzia_lo_stato_corrente() -> None:
    client, _ = crea_client()

    html = client.get("/capitolo/r1/1").text  # Funzioni: da ripassare

    selettore = html[html.index('id="stato-selettore"') :]
    premuti = re.findall(r'stato/(\w+)"[^<]*>\s*<button[^>]*aria-pressed="true"', selettore)
    assert premuti == ["da_ripassare"]


# ---------- risorse statiche ----------


def test_stile_e_htmx_sono_serviti_dall_app() -> None:
    client, _ = crea_client()

    assert client.get("/static/stile.css").status_code == 200
    assert client.get("/static/htmx.min.js").status_code == 200


# ---------- difesa da richieste da altri siti ----------


def test_un_post_dichiarato_cross_site_dal_browser_viene_rifiutato() -> None:
    client, lettura = crea_client()

    risposta = client.post(
        "/capitolo/r1/0/stato/in_corso", headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert risposta.status_code == 403
    assert lettura.lezioni()[0].capitoli[0].stato is S.COMPRESO  # invariato


def test_un_post_dello_stesso_sito_o_senza_intestazione_passa() -> None:
    client, _ = crea_client()

    stesso = client.post(
        "/capitolo/r1/0/stato/in_corso",
        headers={"Sec-Fetch-Site": "same-origin"},
        follow_redirects=False,
    )
    senza = client.post("/capitolo/r1/0/stato/compreso", follow_redirects=False)

    assert stesso.status_code == 303 and senza.status_code == 303


# ---------- schede della materia: glossario e da ripassare ----------

from trascrizione_lezioni.studio import percorso_capitolo  # noqa: E402


def crea_client_con_appunti() -> tuple[TestClient, LetturaStudioFake]:
    dettagli = {
        ("r1", 0): (
            "t",
            AppuntiCapitolo(
                riassunto="R.",
                termini=[
                    Termine("Insieme", "Collezione di elementi."),
                    Termine("Èra", "Un periodo."),
                ],
                da_ripassare=["Differenza tra appartenenza e inclusione"],
            ),
        ),
        ("r2", 0): (
            "t",
            AppuntiCapitolo(
                riassunto="R.",
                termini=[
                    Termine("insieme", "Oggetto della teoria degli insiemi."),
                    Termine("Dominio", "L'insieme di partenza."),
                ],
                da_ripassare=["Il dominio deve essere non vuoto", "Definizione di limite"],
            ),
        ),
    }
    return crea_client(dettagli=dettagli)


def test_l_hub_ha_le_tre_schede_con_quella_corrente_evidenziata() -> None:
    client, _ = crea_client()

    html = client.get("/materia/Analisi").text

    nav = html[html.index('class="sezioni"') : html.index("</nav>", html.index('class="sezioni"'))]
    assert 'href="/materia/Analisi/glossario"' in nav
    assert 'href="/materia/Analisi/da-ripassare"' in nav
    assert nav.count('aria-current="page"') == 1
    assert 'aria-current="page">Lezioni' in nav or 'aria-current="page"' in nav.split("Lezioni")[0]


def test_il_glossario_aggrega_i_termini_di_piu_lezioni_in_ordine_alfabetico() -> None:
    client, _ = crea_client_con_appunti()

    risposta = client.get("/materia/Analisi/glossario")

    assert risposta.status_code == 200
    html = risposta.text
    ordine = [html.index(t) for t in ("Dominio", "Èra", "Insieme")]
    assert ordine == sorted(ordine)
    # Lo stesso termine in due Lezioni: una voce, due definizioni, ciascuna con la sua fonte.
    assert html.count("Insieme</dt>") == 1 or html.count(">Insieme<") == 1
    assert "Collezione di elementi." in html and "Oggetto della teoria degli insiemi." in html
    assert f'href="{percorso_capitolo("r1", 0)}"' in html
    assert f'href="{percorso_capitolo("r2", 0)}"' in html
    assert "01/09/2026" in html and "08/09/2026" in html


def test_la_ricerca_nel_glossario_filtra_per_termine_e_definizione() -> None:
    client, _ = crea_client_con_appunti()

    per_termine = client.get("/materia/Analisi/glossario", params={"q": "domin"}).text
    per_definizione = client.get("/materia/Analisi/glossario", params={"q": "periodo"}).text

    assert "Dominio" in per_termine and "Èra" not in per_termine
    assert "Èra" in per_definizione and "Dominio" not in per_definizione


def test_una_ricerca_senza_risultati_lo_dice() -> None:
    client, _ = crea_client_con_appunti()

    html = client.get("/materia/Analisi/glossario", params={"q": "zzz"}).text

    assert "Nessun termine" in html and "zzz" in html


def test_il_campo_di_ricerca_funziona_anche_senza_javascript_e_riprende_il_testo() -> None:
    client, _ = crea_client_con_appunti()

    html = client.get("/materia/Analisi/glossario", params={"q": "domin"}).text

    assert 'method="get"' in html and 'name="q"' in html and 'value="domin"' in html


def test_il_glossario_senza_termini_ha_un_messaggio_vuoto() -> None:
    client, _ = crea_client()  # gli appunti di prova non hanno termini

    assert "Nessun termine" in client.get("/materia/Analisi/glossario").text


def test_da_ripassare_raccoglie_i_passaggi_del_docente_per_capitolo_dal_piu_recente() -> None:
    client, _ = crea_client_con_appunti()

    risposta = client.get("/materia/Analisi/da-ripassare")

    assert risposta.status_code == 200
    html = risposta.text
    assert html.index("Definizione di limite") < html.index("Differenza tra appartenenza")
    assert "Il dominio deve essere non vuoto" in html
    assert f'href="{percorso_capitolo("r2", 0)}"' in html
    assert f'href="{percorso_capitolo("r1", 0)}"' in html


def test_da_ripassare_senza_passaggi_ha_un_messaggio_vuoto() -> None:
    client, _ = crea_client()

    assert "Nessun passaggio" in client.get("/materia/Analisi/da-ripassare").text


def test_le_schede_di_una_materia_sconosciuta_danno_404() -> None:
    client, _ = crea_client()

    assert client.get("/materia/Astrologia/glossario").status_code == 404
    assert client.get("/materia/Astrologia/da-ripassare").status_code == 404


def test_una_materia_corrente_senza_lezioni_ha_schede_vuote_ma_esistenti() -> None:
    client, _ = crea_client(lezioni=[], materie=["Analisi"])

    assert client.get("/materia/Analisi/glossario").status_code == 200
    assert client.get("/materia/Analisi/da-ripassare").status_code == 200


# ---------- indicatore "nuovo" ----------


def lezioni_con_nuovi() -> list[LezioneStudio]:
    return [
        LezioneStudio(
            "l1", "Analisi", date(2026, 9, 1), None,
            [
                CapitoloStudio("r1", 0, "Insiemi", S.DA_STUDIARE, 1, nuovo=True),
                CapitoloStudio("r1", 1, "Funzioni", S.DA_STUDIARE, 2, nuovo=False),
            ],
        )
    ]


def test_i_capitoli_non_ancora_aperti_hanno_l_indicatore_nuovo_nell_hub() -> None:
    client, _ = crea_client(lezioni=lezioni_con_nuovi())

    html = client.get("/materia/Analisi").text

    voci = re.findall(r"<li>.*?</li>", html, re.S)
    riga_insiemi = next(v for v in voci if "Insiemi" in v)
    riga_funzioni = next(v for v in voci if "Funzioni" in v)
    assert 'class="nuovo"' in riga_insiemi
    assert 'class="nuovo"' not in riga_funzioni


def test_la_dashboard_conta_i_capitoli_nuovi_della_materia() -> None:
    client, _ = crea_client(lezioni=lezioni_con_nuovi())

    scheda = client.get("/").text
    scheda = scheda[scheda.index('data-materia="Analisi"') :]
    scheda = scheda[: scheda.index("</article>")]

    assert "1 nuovo" in scheda


def test_aprire_un_capitolo_lo_toglie_da_nuovo_ovunque() -> None:
    client, lettura = crea_client(lezioni=lezioni_con_nuovi())
    assert lettura.lezioni()[0].capitoli[0].nuovo is True

    assert client.get("/capitolo/r1/0").status_code == 200

    assert lettura.lezioni()[0].capitoli[0].nuovo is False
    assert "1 nuovo" not in client.get("/").text
    assert 'class="nuovo"' not in client.get("/materia/Analisi").text


def test_nella_linea_del_tempo_i_capitoli_nuovi_si_riconoscono() -> None:
    client, _ = crea_client(lezioni=lezioni_con_nuovi())

    html = client.get("/capitolo/r1/1").text  # apre il secondo: il primo resta nuovo

    timeline = html[html.index('id="timeline"') : html.index("</nav>", html.index('id="timeline"'))]
    assert "nuovo" in timeline.split("Funzioni")[0]  # nell'etichetta del primo passo


def test_cambiare_lo_stato_non_conta_come_aprire_il_capitolo() -> None:
    client, lettura = crea_client(lezioni=lezioni_con_nuovi())

    client.post("/capitolo/r1/0/stato/compreso", follow_redirects=False)

    assert lettura.lezioni()[0].capitoli[0].nuovo is True


def test_il_percorso_di_un_capitolo_apre_la_pagina_giusta() -> None:
    client, _ = crea_client()

    risposta = client.get(percorso_capitolo("r1", 1))

    assert risposta.status_code == 200
    assert "Funzioni" in risposta.text
