"""Avvia il sito di studio. Esegui con: uv run python -m trascrizione_lezioni.web_run

Ascolta di default solo su 127.0.0.1: si espone all'iPhone con `tailscale serve`
(vedi README), così il sito non è raggiungibile da altre reti."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import uvicorn
from dotenv import load_dotenv

from .adapters.postgres_studio import LetturaStudioPostgres
from .config import carica_materie_correnti
from .studio import LetturaStudio
from .web.app import crea_app

RADICE_PROGETTO = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    database_url = _leggi_env_obbligatoria("DATABASE_URL")
    host = os.environ.get("WEB_HOST") or "127.0.0.1"
    porta = int(os.environ.get("WEB_PORT") or 8000)
    materie_correnti = carica_materie_correnti(RADICE_PROGETTO / "config" / "materie.yaml")

    @contextmanager
    def apri_lettura() -> Iterator[LetturaStudio]:
        # Una connessione per richiesta: le richieste girano in thread diversi.
        with psycopg.connect(database_url) as connessione:
            yield LetturaStudioPostgres(connessione)

    uvicorn.run(crea_app(apri_lettura, materie_correnti), host=host, port=porta)


def _leggi_env_obbligatoria(nome: str) -> str:
    valore = os.environ.get(nome)
    if not valore:
        raise RuntimeError(f"Variabile d'ambiente {nome} mancante o vuota (vedi .env.example)")
    return valore


if __name__ == "__main__":
    main()
