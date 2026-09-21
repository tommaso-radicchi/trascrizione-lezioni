"""Adapter reale per la segmentazione in Capitoli via Ollama (vedi ADR 0003).

Il modello non riscrive la Trascrizione: restituisce solo titolo e frase di inizio
di ogni Capitolo, e il taglio del testo lo fa il codice (vedi segmentazione.py).

Adapter sottile: non coperto dal seam principale di test."""

from __future__ import annotations

from typing import Any

import httpx

from ..dominio import PropostaCapitolo
from ..segmentazione import SegmentazioneNonValida
from .ollama import NUM_CTX_DEFAULT, chiedi_json

SISTEMA_SEGMENTAZIONE = (
    "Sei un assistente che divide la trascrizione di una lezione universitaria in italiano "
    "in capitoli tematici, nell'ordine in cui compaiono. Un capitolo per argomento, ciascuno "
    "di circa 1500-2500 parole. Per ogni capitolo dai un titolo breve e descrittivo e la "
    "frase di inizio: le prime 6-10 parole del capitolo, copiate ESATTAMENTE come compaiono "
    "nella trascrizione, senza correggerle né riassumerle. Il primo capitolo inizia dall'inizio "
    "della trascrizione. Rispondi solo con un oggetto JSON con la chiave \"capitoli\" (lista "
    "di oggetti con \"titolo\" e \"frase_inizio\"), senza testo prima o dopo."
)

SCHEMA_SEGMENTAZIONE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "capitoli": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titolo": {"type": "string"},
                    "frase_inizio": {"type": "string"},
                },
                "required": ["titolo", "frase_inizio"],
            },
        }
    },
    "required": ["capitoli"],
}


class SegmentatoreOllama:
    def __init__(
        self,
        *,
        base_url: str,
        modello: str,
        num_ctx: int = NUM_CTX_DEFAULT,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url
        self._modello = modello
        self._num_ctx = num_ctx
        self._client = client or httpx.Client(timeout=300.0)

    def proponi_capitoli(self, trascrizione: str) -> list[PropostaCapitolo]:
        try:
            dati = chiedi_json(
                self._client,
                base_url=self._base_url,
                modello=self._modello,
                num_ctx=self._num_ctx,
                schema=SCHEMA_SEGMENTAZIONE,
                sistema=SISTEMA_SEGMENTAZIONE,
                utente=f"Trascrizione:\n{trascrizione}",
            )
        except ValueError as errore:
            # Risposta vuota, senza JSON o con JSON malformato: il modello ha risposto male.
            # Gli errori di trasporto (httpx) non finiscono qui e si propagano.
            raise SegmentazioneNonValida(str(errore)) from errore

        try:
            return [
                PropostaCapitolo(titolo=str(voce["titolo"]), frase_inizio=str(voce["frase_inizio"]))
                for voce in dati["capitoli"]
            ]
        except (KeyError, TypeError) as errore:
            raise SegmentazioneNonValida(
                f"La risposta di Ollama non ha la forma attesa ({errore!r})"
            ) from errore
