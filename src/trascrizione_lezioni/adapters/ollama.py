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
import re
from datetime import date
from typing import Any

import httpx

SISTEMA = (
    "Sei un assistente che estrae appunti di studio da una trascrizione di lezione "
    "universitaria in italiano: un riassunto breve (3-5 frasi), i punti chiave, ed "
    "eventuali termini o definizioni specifiche menzionate (lista vuota se non ce ne sono). "
    "Rispondi solo con un oggetto JSON con le chiavi \"riassunto\" (stringa), \"punti_chiave\" "
    "(lista di stringhe) e \"argomenti_e_termini\" (lista di oggetti con \"termine\" e "
    "\"definizione\"), senza testo prima o dopo. Non usare LaTeX né backslash: scrivi i simboli matematici "
    "in Unicode (Ω, ∪, ∩, ∈)."
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
) -> dict[str, Any]:
    """Una chiamata a Ollama con risposta vincolata da JSON Schema. Solleva ValueError
    se la risposta è vuota o non contiene JSON; gli errori HTTP si propagano."""
    risposta = client.post(
        f"{base_url}/api/chat",
        json={
            "model": modello,
            "format": schema,
            # Ollama locale usa 4096 di default e tronca le trascrizioni lunghe.
            "options": {"num_ctx": num_ctx},
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

    def genera_appunti(self, trascrizione: str, materia: str, data: date) -> str:
        contenuto = self._genera_contenuto(trascrizione, materia)
        data_leggibile = data.strftime("%d/%m/%Y")
        return f"# {materia}\n\n**Data**: {data_leggibile}\n\n{contenuto}"

    def _genera_contenuto(self, trascrizione: str, materia: str) -> str:
        appunti = chiedi_json(
            self._client,
            base_url=self._base_url,
            modello=self._modello,
            num_ctx=self._num_ctx,
            schema=SCHEMA_APPUNTI,
            sistema=SISTEMA,
            utente=f"Materia: {materia}\n\nTrascrizione:\n{trascrizione}",
        )
        return _componi_markdown(appunti)


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
