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
