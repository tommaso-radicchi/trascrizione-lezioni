"""GestoreIngest: riceve l'audio dal fratello via bot e crea la Lezione."""

from __future__ import annotations

import uuid
from datetime import date

from .dominio import Lezione, Stato
from .porte import ClientTelegram, Repository


class GestoreIngest:
    def __init__(
        self,
        *,
        repository: Repository,
        client_telegram: ClientTelegram,
        materie_correnti: list[str],
        admin_chat_id: str,
        fratello_chat_id: str | None = None,
    ) -> None:
        self._repository = repository
        self._client_telegram = client_telegram
        self._materie_correnti = materie_correnti
        self._admin_chat_id = admin_chat_id
        self._fratello_chat_id = fratello_chat_id
        self._audio_in_attesa: dict[str, str] = {}

    def e_chat_admin(self, chat_id: str) -> bool:
        return chat_id == self._admin_chat_id

    def _chat_autorizzata(self, chat_id: str) -> bool:
        if self._fratello_chat_id is None:
            return True
        return self.e_chat_admin(chat_id) or chat_id == self._fratello_chat_id

    def audio_ricevuto(self, *, chat_id: str, percorso_audio: str) -> None:
        if not self._chat_autorizzata(chat_id):
            return
        self._audio_in_attesa[chat_id] = percorso_audio
        self._client_telegram.chiedi_materia(chat_id, self._materie_correnti)

    def materia_selezionata(self, *, chat_id: str, materia: str) -> Lezione | None:
        if not self._chat_autorizzata(chat_id):
            return None
        if materia not in self._materie_correnti:
            return None

        percorso_audio = self._audio_in_attesa.pop(chat_id, None)
        if percorso_audio is None:
            return None

        lezione = Lezione(
            id=str(uuid.uuid4()),
            materia=materia,
            data=date.today(),
            percorso_audio=percorso_audio,
            chat_id=chat_id,
            stato=Stato.RICEVUTA,
        )
        self._repository.salva(lezione)
        self._client_telegram.conferma_ricezione(chat_id)
        return lezione
