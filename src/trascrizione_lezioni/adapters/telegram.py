"""Adapter reale per Telegram: chiamate dirette alla Bot API via HTTP (niente
libreria async: il core del sistema è sincrono, vedi orchestratore.py).

Adapter sottile: non coperto dal seam principale di test (vedi issue #1,
sezione Testing Decisions) — il comportamento che conta è testato a monte,
in GestoreIngest e Orchestratore, con i fake.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ..dominio import Lezione
from ..ingest import GestoreIngest

LIMITE_MESSAGGIO_TELEGRAM = 4000

logger = logging.getLogger(__name__)


class ClientTelegramReale:
    def __init__(self, token: str, admin_chat_id: str, timeout: float = 30.0) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._admin_chat_id = admin_chat_id
        self._client = httpx.Client(timeout=timeout)

    def invia_appunti(self, lezione: Lezione, percorso_appunti: str) -> None:
        contenuto = Path(percorso_appunti).read_text(encoding="utf-8")
        if len(contenuto) <= LIMITE_MESSAGGIO_TELEGRAM:
            self._invia_messaggio(lezione.chat_id, contenuto)
        else:
            self._invia_documento(lezione.chat_id, Path(percorso_appunti))

    def notifica_errore(self, lezione: Lezione, messaggio: str) -> None:
        testo = f"⚠️ Errore sulla Lezione di {lezione.materia} del {lezione.data}: {messaggio}"
        self._invia_messaggio(self._admin_chat_id, testo)

    def chiedi_materia(self, chat_id: str, materie: list[str]) -> None:
        tastiera = {
            "inline_keyboard": [[{"text": materia, "callback_data": materia}] for materia in materie]
        }
        self._client.post(
            f"{self._base_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "Di che materia è questa lezione?",
                "reply_markup": tastiera,
            },
        ).raise_for_status()

    def conferma_ricezione(self, chat_id: str) -> None:
        self._invia_messaggio(chat_id, "✅ Ricevuto, i tuoi appunti saranno pronti a breve.")

    def rispondi_al_bottone(self, callback_query_id: str) -> None:
        self._client.post(
            f"{self._base_url}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
        ).raise_for_status()

    def _invia_messaggio(self, chat_id: str, testo: str) -> None:
        self._client.post(
            f"{self._base_url}/sendMessage",
            json={"chat_id": chat_id, "text": testo},
        ).raise_for_status()

    def _invia_documento(self, chat_id: str, percorso: Path) -> None:
        with percorso.open("rb") as file_appunti:
            self._client.post(
                f"{self._base_url}/sendDocument",
                data={"chat_id": chat_id},
                files={"document": (percorso.name, file_appunti, "text/markdown")},
            ).raise_for_status()

    def scarica_audio(self, file_id: str, cartella_destinazione: Path) -> str:
        risposta = self._client.get(f"{self._base_url}/getFile", params={"file_id": file_id})
        risposta.raise_for_status()
        percorso_remoto = risposta.json()["result"]["file_path"]
        token = self._base_url.rsplit("/bot", 1)[1]
        url_file = f"https://api.telegram.org/file/bot{token}/{percorso_remoto}"

        cartella_destinazione.mkdir(parents=True, exist_ok=True)
        percorso_locale = cartella_destinazione / f"{file_id}-{Path(percorso_remoto).name}"
        with self._client.stream("GET", url_file) as flusso:
            flusso.raise_for_status()
            with percorso_locale.open("wb") as f:
                for chunk in flusso.iter_bytes():
                    f.write(chunk)
        return str(percorso_locale)


def esegui_polling(
    *,
    client: ClientTelegramReale,
    gestore_ingest: GestoreIngest,
    token: str,
    cartella_audio: Path,
    offset_iniziale: int = 0,
) -> None:
    """Long-polling su getUpdates. Blocca finché il processo non viene fermato."""

    base_url = f"https://api.telegram.org/bot{token}"
    http = httpx.Client(timeout=60.0)
    offset = offset_iniziale

    while True:
        try:
            risposta = http.get(
                f"{base_url}/getUpdates", params={"offset": offset, "timeout": 30}
            )
            risposta.raise_for_status()
            aggiornamenti = risposta.json()["result"]
        except httpx.HTTPError:
            logger.exception("getUpdates fallito, ritento al prossimo giro")
            continue

        for aggiornamento in aggiornamenti:
            offset = aggiornamento["update_id"] + 1
            _gestisci_aggiornamento(aggiornamento, client, gestore_ingest, cartella_audio)


def _gestisci_aggiornamento(
    aggiornamento: dict[str, object],
    client: ClientTelegramReale,
    gestore_ingest: GestoreIngest,
    cartella_audio: Path,
) -> None:
    messaggio = aggiornamento.get("message")
    if isinstance(messaggio, dict):
        _gestisci_messaggio(messaggio, client, gestore_ingest, cartella_audio)
        return

    callback = aggiornamento.get("callback_query")
    if isinstance(callback, dict):
        _gestisci_callback(callback, client, gestore_ingest)


def _gestisci_messaggio(
    messaggio: dict[str, object],
    client: ClientTelegramReale,
    gestore_ingest: GestoreIngest,
    cartella_audio: Path,
) -> None:
    chat = messaggio.get("chat")
    if not isinstance(chat, dict):
        return
    chat_id = str(chat["id"])

    file_audio = messaggio.get("voice") or messaggio.get("audio") or _documento_audio(messaggio)
    if not isinstance(file_audio, dict):
        return

    file_id = file_audio["file_id"]
    try:
        percorso_audio = client.scarica_audio(str(file_id), cartella_audio)
    except httpx.HTTPError:
        logger.exception("Download audio fallito per chat_id=%s", chat_id)
        return

    gestore_ingest.audio_ricevuto(chat_id=chat_id, percorso_audio=percorso_audio)


def _documento_audio(messaggio: dict[str, object]) -> dict[str, object] | None:
    """Un documento allegato conta come audio solo se il MIME type lo è
    davvero (Telegram manda file audio anche come 'document', non solo
    come 'audio'/'voice', ma un PDF non deve essere trattato come lezione)."""

    documento = messaggio.get("document")
    if not isinstance(documento, dict):
        return None
    mime_type = documento.get("mime_type")
    if not isinstance(mime_type, str) or not mime_type.startswith("audio/"):
        return None
    return documento


def _gestisci_callback(
    callback: dict[str, object],
    client: ClientTelegramReale,
    gestore_ingest: GestoreIngest,
) -> None:
    messaggio = callback.get("message")
    if not isinstance(messaggio, dict):
        return
    chat = messaggio.get("chat")
    if not isinstance(chat, dict):
        return
    chat_id = str(chat["id"])
    materia = str(callback["data"])

    gestore_ingest.materia_selezionata(chat_id=chat_id, materia=materia)
    client.rispondi_al_bottone(str(callback["id"]))
