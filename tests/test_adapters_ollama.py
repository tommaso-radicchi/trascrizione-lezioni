from __future__ import annotations

from datetime import date

import httpx

from trascrizione_lezioni.adapters.ollama import ClientAppuntiOllama


def test_genera_appunti_include_titolo_data_e_contenuto_del_modello() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        assert richiesta.url.path == "/api/generate"
        corpo = httpx.Request("POST", richiesta.url, content=richiesta.content).content
        assert b"Fisica 1" in corpo
        assert b"la lezione parla di attrito" in corpo
        return httpx.Response(
            200,
            json={"response": "## Riassunto\nLa lezione parla di attrito.\n\n## Punti chiave\n- attrito statico\n"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ClientAppuntiOllama(base_url="http://msi.test:11434", modello="test-model", client=client)

    markdown = adapter.genera_appunti("la lezione parla di attrito", "Fisica 1", date(2026, 3, 5))

    assert markdown.startswith("# Fisica 1")
    assert "05/03/2026" in markdown
    assert "## Riassunto" in markdown
    assert "## Punti chiave" in markdown
    assert "attrito statico" in markdown
