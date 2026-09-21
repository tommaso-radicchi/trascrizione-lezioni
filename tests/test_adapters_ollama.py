from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from trascrizione_lezioni.adapters.ollama import ClientAppuntiOllama


def test_genera_appunti_include_titolo_data_e_le_tre_sezioni_dal_json_strutturato() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        assert richiesta.url.path == "/api/chat"
        corpo = json.loads(richiesta.content)
        assert corpo["format"]["type"] == "object"
        assert corpo["options"]["num_ctx"] == 32768
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


def _adapter_con_contenuto(contenuto: str, **extra: object) -> ClientAppuntiOllama:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": contenuto}, **extra})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ClientAppuntiOllama(base_url="http://msi.test:11434", modello="test-model", client=client)


def test_genera_appunti_tollera_testo_e_code_fence_attorno_al_json() -> None:
    appunti = {"riassunto": "Riassunto.", "punti_chiave": ["punto 1"], "argomenti_e_termini": []}
    contenuto = f"Ecco gli appunti:\n```json\n{json.dumps(appunti)}\n```"

    markdown = _adapter_con_contenuto(contenuto).genera_appunti("t", "Fisica 1", date(2026, 3, 5))

    assert "## Riassunto\nRiassunto." in markdown


def test_genera_appunti_con_risposta_vuota_solleva_errore_esplicito() -> None:
    adapter = _adapter_con_contenuto("", done_reason="length")

    with pytest.raises(ValueError, match="risposta vuota.*length"):
        adapter.genera_appunti("t", "Fisica 1", date(2026, 3, 5))


def test_genera_appunti_senza_json_solleva_errore_esplicito() -> None:
    adapter = _adapter_con_contenuto("Non so cosa rispondere")

    with pytest.raises(ValueError, match="non contiene JSON"):
        adapter.genera_appunti("t", "Fisica 1", date(2026, 3, 5))


def test_genera_appunti_tollera_backslash_latex_non_validi_nel_json() -> None:
    contenuto = (
        '{"riassunto": "Insieme mondo $\\Omega$.", "punti_chiave": ["A \\cup B"], '
        '"argomenti_e_termini": []}'
    )

    markdown = _adapter_con_contenuto(contenuto).genera_appunti("t", "Fisica 1", date(2026, 3, 5))

    assert "$\\Omega$" in markdown
    assert "- A \\cup B" in markdown
