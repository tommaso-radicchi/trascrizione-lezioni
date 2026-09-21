"""Il sito di studio: dashboard per Materia, hub delle Lezioni e lettura per Capitolo
(vedi ADR 0003 e issue #14). App privata sul Mac Mini, senza login: si raggiunge solo
via Tailscale. Legge tramite la porta `LetturaStudio`, quindi si prova con un fake."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..dominio import StatoComprensione
from ..studio import (
    ETICHETTE_STATO,
    ORDINE_STATI,
    LetturaStudio,
    barra_segmentata,
    colore_materia,
    da_ripassare,
    riepilogo_materie,
)

CARTELLA = Path(__file__).parent

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]  # fmt: skip

# L'ordine in cui il fratello sceglie lo stato: dal non iniziato al da rivedere.
STATI_SELETTORE = (
    StatoComprensione.DA_STUDIARE,
    StatoComprensione.IN_CORSO,
    StatoComprensione.COMPRESO,
    StatoComprensione.DA_RIPASSARE,
)

NOMI_CONTATORE: dict[StatoComprensione, tuple[str, str]] = {
    StatoComprensione.COMPRESO: ("compreso", "compresi"),
    StatoComprensione.IN_CORSO: ("in corso", "in corso"),
    StatoComprensione.DA_RIPASSARE: ("da ripassare", "da ripassare"),
    StatoComprensione.DA_STUDIARE: ("da studiare", "da studiare"),
}


def _data_estesa(giorno: date) -> str:
    return f"{GIORNI[giorno.weekday()]} {giorno.day} {MESI[giorno.month - 1]}"


def _testo_contatore(stato: StatoComprensione, quanti: int) -> str:
    singolare, plurale = NOMI_CONTATORE[stato]
    return f"{quanti} {singolare if quanti == 1 else plurale}"


def crea_app(
    apri_lettura: Callable[[], AbstractContextManager[LetturaStudio]],
    materie_correnti: list[str],
) -> FastAPI:
    """`apri_lettura` dà una lettura per richiesta (una connessione al DB per richiesta:
    le richieste girano in thread diversi e una connessione non va condivisa)."""
    app = FastAPI(title="Studio", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=CARTELLA / "static"), name="static")

    modelli = Jinja2Templates(directory=CARTELLA / "templates")
    modelli.env.filters.update(
        quota=lambda testo: quote(str(testo), safe=""),
        colore_materia=lambda materia: colore_materia(materia, materie_correnti),
        data_breve=lambda giorno: giorno.strftime("%d/%m"),
        data_completa=lambda giorno: giorno.strftime("%d/%m/%Y"),
        data_estesa=_data_estesa,
    )
    modelli.env.globals.update(
        ORDINE_STATI=ORDINE_STATI,
        STATI_SELETTORE=STATI_SELETTORE,
        ETICHETTE_STATO=ETICHETTE_STATO,
        testo_contatore=_testo_contatore,
        barra_segmentata=barra_segmentata,
    )

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> Response:
        with apri_lettura() as lettura:
            lezioni = lettura.lezioni()
        return modelli.TemplateResponse(
            request,
            "dashboard.html",
            {
                "oggi": date.today(),
                "ripasso": da_ripassare(lezioni),
                "riepiloghi": riepilogo_materie(lezioni, materie_correnti),
            },
        )

    @app.get("/materia/{materia}", response_class=HTMLResponse)
    def hub_materia(request: Request, materia: str) -> Response:
        with apri_lettura() as lettura:
            lezioni = [l for l in lettura.lezioni() if l.materia == materia]
        if not lezioni and materia not in materie_correnti:
            raise HTTPException(status_code=404, detail="Materia non trovata")
        (riepilogo,) = riepilogo_materie(lezioni, [materia])
        return modelli.TemplateResponse(
            request,
            "materia.html",
            {
                "materia": materia,
                "riepilogo": riepilogo,
                "lezioni": sorted(lezioni, key=lambda lezione: lezione.data, reverse=True),
            },
        )

    @app.get("/capitolo/{registrazione_id}/{posizione}", response_class=HTMLResponse)
    def capitolo(request: Request, registrazione_id: str, posizione: int) -> Response:
        with apri_lettura() as lettura:
            dettaglio = lettura.dettaglio_capitolo(registrazione_id, posizione)
        if dettaglio is None:
            raise HTTPException(status_code=404, detail="Capitolo non trovato")
        capitoli = dettaglio.lezione.capitoli
        indice = dettaglio.capitolo.numero - 1
        return modelli.TemplateResponse(
            request,
            "capitolo.html",
            {
                "d": dettaglio,
                "precedente": capitoli[indice - 1] if indice > 0 else None,
                "successivo": capitoli[indice + 1] if indice + 1 < len(capitoli) else None,
            },
        )

    @app.post("/capitolo/{registrazione_id}/{posizione}/stato/{stato}")
    def imposta_stato(
        request: Request, registrazione_id: str, posizione: int, stato: str
    ) -> Response:
        # Un browser dichiara da solo se la richiesta parte da un altro sito: il sito non ha
        # login, quindi una pagina qualunque aperta sulla tailnet non deve poter cambiare gli stati.
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(status_code=403, detail="Richiesta da un altro sito")
        try:
            nuovo_stato = StatoComprensione(stato)
        except ValueError:
            raise HTTPException(status_code=404, detail="Stato sconosciuto") from None

        with apri_lettura() as lettura:
            if not lettura.imposta_stato(registrazione_id, posizione, nuovo_stato):
                raise HTTPException(status_code=404, detail="Capitolo non trovato")
            dettaglio = lettura.dettaglio_capitolo(registrazione_id, posizione)

        if request.headers.get("HX-Request") and dettaglio is not None:
            return modelli.TemplateResponse(request, "_aggiornamento_stato.html", {"d": dettaglio})
        return RedirectResponse(f"/capitolo/{registrazione_id}/{posizione}", status_code=303)

    return app
