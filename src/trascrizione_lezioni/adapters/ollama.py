"""Adapter reale per la generazione degli Appunti via Ollama sull'MSI.
Chiamato sempre dopo la trascrizione, mai in parallelo (vedi ADR 0002):
l'Orchestratore processa una Lezione alla volta, un passo alla volta, quindi
questo adapter non deve occuparsi lui stesso della sequenzialità.

Usa un JSON Schema (parametro `format` di Ollama) per vincolare l'output,
invece di chiedere il Markdown a parole: modelli anche di taglia elevata
(verificato su gemma4:e4b e gemma4:12b) ignorano un'intestazione richiesta
solo nel prompt, mentre uno schema vincola l'output a livello di generazione.
Il Markdown finale è composto qui, deterministicamente, dai campi estratti.

Adapter sottile: non coperto dal seam principale di test."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx

SISTEMA = (
    "Sei un assistente che estrae appunti di studio da una trascrizione di lezione "
    "universitaria in italiano: un riassunto breve (3-5 frasi), i punti chiave, ed "
    "eventuali termini o definizioni specifiche menzionate (lista vuota se non ce ne sono)."
)

SCHEMA_APPUNTI: dict[str, Any] = {
    "type": "object",
    "properties": {
        "riassunto": {"type": "string"},
        "punti_chiave": {"type": "array", "items": {"type": "string"}},
        "argomenti_e_termini": {
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
    },
    "required": ["riassunto", "punti_chiave", "argomenti_e_termini"],
}


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
        risposta = self._client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._modello,
                "format": SCHEMA_APPUNTI,
                "messages": [
                    {"role": "system", "content": SISTEMA},
                    {
                        "role": "user",
                        "content": f"Materia: {materia}\n\nTrascrizione:\n{trascrizione}",
                    },
                ],
                "stream": False,
            },
        )
        risposta.raise_for_status()
        appunti = json.loads(risposta.json()["message"]["content"])
        return _componi_markdown(appunti)


def _componi_markdown(appunti: dict[str, Any]) -> str:
    sezioni = [
        "## Riassunto",
        str(appunti["riassunto"]).strip(),
        "",
        "## Punti chiave",
        "\n".join(f"- {punto}" for punto in appunti["punti_chiave"]),
    ]

    argomenti = appunti.get("argomenti_e_termini") or []
    if argomenti:
        sezioni += [
            "",
            "## Argomenti e termini",
            "\n".join(f"- **{voce['termine']}**: {voce['definizione']}" for voce in argomenti),
        ]

    return "\n".join(sezioni)
