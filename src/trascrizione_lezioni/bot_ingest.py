"""Avvia il bot Telegram di ingest: riceve l'audio, fa scegliere la Materia,
crea la Lezione su Postgres. Esegui con: uv run python -m trascrizione_lezioni.bot_ingest
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .adapters.postgres import RepositoryPostgres
from .adapters.telegram import ClientTelegramReale, esegui_polling
from .config import carica_materie_correnti
from .ingest import GestoreIngest

RADICE_PROGETTO = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    token = _leggi_env_obbligatoria("TELEGRAM_BOT_TOKEN")
    admin_chat_id = _leggi_env_obbligatoria("TELEGRAM_ADMIN_CHAT_ID")
    database_url = _leggi_env_obbligatoria("DATABASE_URL")
    fratello_chat_id = os.environ.get("TELEGRAM_FRATELLO_CHAT_ID") or None

    materie_correnti = carica_materie_correnti(RADICE_PROGETTO / "config" / "materie.yaml")
    cartella_audio = RADICE_PROGETTO / "audio_in_entrata"

    connessione = psycopg.connect(database_url)
    repository = RepositoryPostgres(connessione)
    client_telegram = ClientTelegramReale(token=token, admin_chat_id=admin_chat_id)
    gestore_ingest = GestoreIngest(
        repository=repository,
        client_telegram=client_telegram,
        materie_correnti=materie_correnti,
        admin_chat_id=admin_chat_id,
        fratello_chat_id=fratello_chat_id,
    )

    if fratello_chat_id is None:
        logging.warning(
            "TELEGRAM_FRATELLO_CHAT_ID non impostata: qualunque chat può avviare un upload."
        )
    logging.info("Bot di ingest avviato, in ascolto...")
    esegui_polling(
        client=client_telegram,
        gestore_ingest=gestore_ingest,
        token=token,
        cartella_audio=cartella_audio,
    )


def _leggi_env_obbligatoria(nome: str) -> str:
    valore = os.environ.get(nome)
    if not valore:
        raise RuntimeError(f"Variabile d'ambiente {nome} mancante o vuota (vedi .env.example)")
    return valore


if __name__ == "__main__":
    main()
