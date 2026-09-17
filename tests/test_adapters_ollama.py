from __future__ import annotations

import json
from datetime import date

import httpx

from trascrizione_lezioni.adapters.ollama import ClientAppuntiOllama


def test_genera_appunti_include_titolo_data_e_le_tre_sezioni_dal_json_strutturato() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        assert richiesta.url.path == "/api/chat"
        corpo = json.loads(richiesta.content)
        assert corpo["format"]["type"] == "object"
        assert "la lezione parla di attrito" in corpo["messages"][1]["content"]

        appunti = {
            "riassunto": "La lezione parla di attrito.",
            "punti_chiave": ["attrito statico", "attrito dinamico"],
            "argomenti_e_termini": [
                {"termine": "Attrito", "definizione": "Forza che si opone al moto relativo."}
            ],
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(appunti)}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ClientAppuntiOllama(base_url="http://msi.test:11434", modello="test-model", client=client)

    markdown = adapter.genera_appunti("la lezione parla di attrito", "Fisica 1", date(2026, 3, 5))

    assert markdown.startswith("# Fisica 1")
    assert "05/03/2026" in markdown
    assert "## Riassunto\nLa lezione parla di attrito." in markdown
    assert "## Punti chiave\n- attrito statico\n- attrito dinamico" in markdown
    assert "## Argomenti e termini\n- **Attrito**: Forza che si opone al moto relativo." in markdown


def test_genera_appunti_omette_la_sezione_argomenti_se_vuota() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        appunti = {
            "riassunto": "Riassunto breve.",
            "punti_chiave": ["punto 1"],
            "argomenti_e_termini": [],
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(appunti)}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ClientAppuntiOllama(base_url="http://msi.test:11434", modello="test-model", client=client)

    markdown = adapter.genera_appunti("trascrizione breve", "Fisica 1", date(2026, 3, 5))

    assert "## Argomenti e termini" not in markdown
