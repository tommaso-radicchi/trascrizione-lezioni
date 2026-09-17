"""Adapter reale per la generazione degli Appunti via Ollama sull'MSI.
Chiamato sempre dopo la trascrizione, mai in parallelo (vedi ADR 0002):
l'Orchestratore processa una Lezione alla volta, un passo alla volta, quindi
questo adapter non deve occuparsi lui stesso della sequenzialità.

Adapter sottile: non coperto dal seam principale di test."""

from __future__ import annotations

from datetime import date

import httpx

PROMPT_TEMPLATE = """Sei un assistente che trasforma la trascrizione di una lezione universitaria di {materia} in appunti di studio.

Genera SOLO il contenuto in Markdown con questa struttura esatta (non aggiungere un titolo con il nome della materia, verrà aggiunto separatamente):

## Riassunto
Un riassunto breve (3-5 frasi) di cosa è stato trattato nella lezione.

## Punti chiave
- punto chiave 1
- punto chiave 2

## Argomenti e termini
- **Termine**: definizione breve
(Includi questa sezione SOLO se nella trascrizione compaiono termini o definizioni specifiche; altrimenti omettila del tutto.)

Trascrizione della lezione:
{trascrizione}
"""


class ClientAppuntiOllama:
    def __init__(self, *, base_url: str, modello: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url
        self._modello = modello
        self._client = client or httpx.Client(timeout=300.0)

    def genera_appunti(self, trascrizione: str, materia: str, data: date) -> str:
        contenuto = self._genera_contenuto(trascrizione, materia)
        data_leggibile = data.strftime("%d/%m/%Y")
        return f"# {materia}\n\n**Data**: {data_leggibile}\n\n{contenuto}"

    def _genera_contenuto(self, trascrizione: str, materia: str) -> str:
        prompt = PROMPT_TEMPLATE.format(materia=materia, trascrizione=trascrizione)
        risposta = self._client.post(
            f"{self._base_url}/api/generate",
            json={"model": self._modello, "prompt": prompt, "stream": False},
        )
        risposta.raise_for_status()
        return str(risposta.json()["response"]).strip()
