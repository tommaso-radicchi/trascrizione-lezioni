"""Esegue il loop dell'Orchestratore con tutti gli adapter reali: controlla
la coda a intervalli, dispacciando trascrizione/appunti/archiviazione/notifica
secondo lo stato di ogni Lezione. Esegui con:
uv run python -m trascrizione_lezioni.orchestratore_run
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .adapters.archivio import ArchivioFile
from .adapters.msi import ClientTrascrizioneMsi, ControlloGpuMsi
from .adapters.ollama import ClientAppuntiOllama
from .adapters.postgres import RepositoryPostgres
from .adapters.telegram import API_BASE_URL_DEFAULT, ClientTelegramReale

from .orchestratore import Orchestratore

RADICE_PROGETTO = Path(__file__).resolve().parent.parent.parent
INTERVALLO_SECONDI = 30.0


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    token = _leggi_env_obbligatoria("TELEGRAM_BOT_TOKEN")
    admin_chat_id = _leggi_env_obbligatoria("TELEGRAM_ADMIN_CHAT_ID")
    database_url = _leggi_env_obbligatoria("DATABASE_URL")
    msi_base_url = _leggi_env_obbligatoria("MSI_BASE_URL")
    msi_mac_address = _leggi_env_obbligatoria("MSI_MAC_ADDRESS")
    ollama_base_url = _leggi_env_obbligatoria("OLLAMA_BASE_URL")
    ollama_model = _leggi_env_obbligatoria("OLLAMA_MODEL")
    api_base_url = os.environ.get("TELEGRAM_API_BASE_URL") or API_BASE_URL_DEFAULT
    cartella_file_locale_env = os.environ.get("TELEGRAM_LOCAL_FILES_DIR")
    cartella_file_locale = Path(cartella_file_locale_env) if cartella_file_locale_env else None

    connessione = psycopg.connect(database_url)
    repository = RepositoryPostgres(connessione)
    client_telegram = ClientTelegramReale(
        token=token,
        admin_chat_id=admin_chat_id,
        api_base_url=api_base_url,
        cartella_file_locale=cartella_file_locale,
    )
    controllo_gpu = ControlloGpuMsi(
        base_url=msi_base_url,
        mac_address=msi_mac_address,
        notifica_irraggiungibile_fn=client_telegram.notifica_stato_admin,
    )
    orchestratore = Orchestratore(
        controllo_gpu=controllo_gpu,
        client_trascrizione=ClientTrascrizioneMsi(base_url=msi_base_url),
        client_appunti=ClientAppuntiOllama(base_url=ollama_base_url, modello=ollama_model),
        archivio=ArchivioFile(cartella_radice=RADICE_PROGETTO / "archivio"),
        repository=repository,
        client_telegram=client_telegram,
    )

    logging.info("Orchestratore avviato, un ciclo ogni %ss...", INTERVALLO_SECONDI)
    while True:
        try:
            orchestratore.elabora_coda()
        except Exception:
            logging.exception("Ciclo dell'Orchestratore fallito, ritento al prossimo giro")
        time.sleep(INTERVALLO_SECONDI)


def _leggi_env_obbligatoria(nome: str) -> str:
    valore = os.environ.get(nome)
    if not valore:
        raise RuntimeError(f"Variabile d'ambiente {nome} mancante o vuota (vedi .env.example)")
    return valore


if __name__ == "__main__":
    main()
