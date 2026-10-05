"""Adapter reale per la generazione degli Appunti via Ollama (sul Mac Mini, con un
modello cloud). L'Orchestratore processa una Registrazione alla volta, un passo alla
volta, quindi questo adapter non deve occuparsi lui stesso della sequenzialità.

Usa un JSON Schema (parametro `format` di Ollama) per vincolare l'output,
invece di chiedere il Markdown a parole: modelli anche di taglia elevata
(verificato su gemma4:e4b e gemma4:12b) ignorano un'intestazione richiesta
solo nel prompt, mentre uno schema vincola l'output a livello di generazione.
Gli Appunti tornano come dati strutturati: il Markdown lo compone il codice (composizione.py).

Adapter sottile: non coperto dal seam principale di test."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import httpx

from ..dominio import AppuntiCapitolo

SISTEMA_CAPITOLO = (
    "Sei un assistente che prepara appunti di studio da un capitolo di una lezione "
    "universitaria in italiano. Produci: un riassunto di 2-3 frasi che dia il quadro generale "
    "del capitolo senza ripetere i punti chiave; i punti chiave, come frasi complete che "
    "contengono i dettagli da ricordare; i termini o le definizioni specifiche menzionate "
    "(lista vuota se non ce ne sono); i passaggi da ripassare, SOLO se il docente ha detto "
    "esplicitamente che sono importanti o richiesti all'esame (lista vuota altrimenti); "
    "2-3 domande aperte di autovalutazione, ciascuna con una risposta breve. "
    "Rispondi solo con un oggetto JSON con le chiavi \"riassunto\" (stringa), "
    "\"punti_chiave\" (lista di stringhe), \"termini\" (lista di oggetti con \"termine\" e "
    "\"definizione\"), \"da_ripassare\" (lista di stringhe) e \"domande\" (lista di oggetti con "
    "\"domanda\" e \"risposta\"), senza testo prima o dopo. Non usare LaTeX né backslash: "
    "scrivi i simboli matematici in Unicode (Ω, ∪, ∩, ∈)."
)

SISTEMA_QUADRO = (
    "Sei un assistente che scrive il quadro generale di una lezione universitaria in "
    "italiano, a partire dai titoli e dai riassunti dei suoi capitoli. Scrivi 2-4 frasi che "
    "dicano di cosa parla la lezione nel suo insieme, senza elencare i capitoli uno per uno. "
    "Rispondi solo con un oggetto JSON con la chiave \"quadro_generale\" (stringa), senza "
    "testo prima o dopo. Non usare LaTeX né backslash: scrivi i simboli in Unicode."
)

SCHEMA_APPUNTI_CAPITOLO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "riassunto": {"type": "string"},
        "punti_chiave": {"type": "array", "items": {"type": "string"}},
        "termini": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "termine": {"type": "string"},
                    "definizione": {"type": "string"},
                },
                "required": ["termine", "definizione"],
            },
        },
        "da_ripassare": {"type": "array", "items": {"type": "string"}},
        "domande": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "domanda": {"type": "string"},
                    "risposta": {"type": "string"},
                },
                "required": ["domanda", "risposta"],
            },
        },
    },
    "required": ["riassunto", "punti_chiave", "termini", "da_ripassare", "domande"],
}

SCHEMA_QUADRO: dict[str, Any] = {
    "type": "object",
    "properties": {"quadro_generale": {"type": "string"}},
    "required": ["quadro_generale"],
}


NUM_CTX_DEFAULT = 32768


def chiedi_json(
    client: httpx.Client,
    *,
    base_url: str,
    modello: str,
    num_ctx: int,
    schema: dict[str, Any],
    sistema: str,
    utente: str,
    temperatura: float | None = None,
) -> dict[str, Any]:
    """Una chiamata a Ollama con risposta vincolata da JSON Schema. Solleva ValueError
    se la risposta è vuota o non contiene JSON; gli errori HTTP si propagano."""
    # Ollama locale usa 4096 di default e tronca le trascrizioni lunghe.
    opzioni: dict[str, Any] = {"num_ctx": num_ctx}
    if temperatura is not None:
        opzioni["temperature"] = temperatura
    risposta = client.post(
        f"{base_url}/api/chat",
        json={
            "model": modello,
            "format": schema,
            "options": opzioni,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": utente},
            ],
            "stream": False,
        },
    )
    risposta.raise_for_status()
    dati = risposta.json()
    contenuto = dati["message"]["content"]
    if not contenuto.strip():
        raise ValueError(
            f"Ollama ha restituito una risposta vuota (done_reason={dati.get('done_reason')}): "
            "la trascrizione potrebbe superare il contesto del modello"
        )
    return estrai_json(contenuto)


class ClientAppuntiOllama:
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

    def genera_appunti_capitolo(self, titolo: str, testo: str, materia: str) -> AppuntiCapitolo:
        dati = self._chiedi(
            SCHEMA_APPUNTI_CAPITOLO,
            SISTEMA_CAPITOLO,
            f"Materia: {materia}\nTitolo del capitolo: {titolo}\n\nTrascrizione del capitolo:\n{testo}",
        )
        return AppuntiCapitolo.da_dict(dati)

    def genera_quadro_generale(
        self, materia: str, data: date, riassunti: list[tuple[str, str]]
    ) -> str:
        elenco = "\n".join(
            f"{numero}. {titolo}: {riassunto}" for numero, (titolo, riassunto) in enumerate(riassunti, 1)
        )
        dati = self._chiedi(
            SCHEMA_QUADRO,
            SISTEMA_QUADRO,
            f"Materia: {materia}\nData: {data.strftime('%d/%m/%Y')}\n\nCapitoli:\n{elenco}",
        )
        quadro = str(dati.get("quadro_generale", "")).strip()
        if not quadro:
            raise ValueError("Ollama non ha restituito il quadro generale")
        return quadro

    def _chiedi(self, schema: dict[str, Any], sistema: str, utente: str) -> dict[str, Any]:
        return chiedi_json(
            self._client,
            base_url=self._base_url,
            modello=self._modello,
            num_ctx=self._num_ctx,
            schema=schema,
            sistema=sistema,
            utente=utente,
        )


def estrai_json(contenuto: str) -> dict[str, Any]:
    # I modelli cloud ignorano il parametro `format`: tollera testo o code fence attorno al JSON.
    inizio, fine = contenuto.find("{"), contenuto.rfind("}")
    if inizio == -1 or fine < inizio:
        raise ValueError(f"La risposta di Ollama non contiene JSON: {contenuto[:200]!r}")
    testo_json = contenuto[inizio : fine + 1]
    try:
        appunti: dict[str, Any] = json.loads(testo_json)
    except json.JSONDecodeError:
        # Backslash isolati (es. LaTeX come \Omega) sono escape JSON non validi: li letteralizza.
        appunti = json.loads(re.sub(r'\\(?!["\\])', r"\\\\", testo_json))
    return appunti
