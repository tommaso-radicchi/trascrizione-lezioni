from __future__ import annotations

import json

import httpx
import pytest

from trascrizione_lezioni.adapters.segmentazione_ollama import SegmentatoreOllama
from trascrizione_lezioni.dominio import PropostaCapitolo
from trascrizione_lezioni.segmentazione import SegmentazioneNonValida


def _segmentatore(handler: httpx.MockTransport | object) -> SegmentatoreOllama:
    client = httpx.Client(transport=handler)  # type: ignore[arg-type]
    return SegmentatoreOllama(base_url="http://mac.test:11434", modello="test-model", client=client)


def _con_contenuto(contenuto: str) -> SegmentatoreOllama:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": contenuto}})

    return _segmentatore(httpx.MockTransport(handler))


def test_proponi_capitoli_manda_la_trascrizione_con_lo_schema_e_restituisce_le_proposte() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        assert richiesta.url.path == "/api/chat"
        corpo = json.loads(richiesta.content)
        assert corpo["format"]["required"] == ["capitoli"]
        assert corpo["options"]["num_ctx"] == 32768
        assert "gli insiemi sono collezioni" in corpo["messages"][1]["content"]
        risposta = {
            "capitoli": [
                {"titolo": "Insiemi", "frase_inizio": "gli insiemi sono"},
                {"titolo": "Funzioni", "frase_inizio": "una funzione associa"},
            ]
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(risposta)}})

    segmentatore = _segmentatore(httpx.MockTransport(handler))

    proposte = segmentatore.proponi_capitoli("gli insiemi sono collezioni. una funzione associa")

    assert proposte == [
        PropostaCapitolo("Insiemi", "gli insiemi sono"),
        PropostaCapitolo("Funzioni", "una funzione associa"),
    ]


def test_proponi_capitoli_tollera_testo_e_code_fence_attorno_al_json() -> None:
    contenuto = '```json\n{"capitoli": [{"titolo": "T", "frase_inizio": "f"}]}\n```'

    assert _con_contenuto(contenuto).proponi_capitoli("t") == [PropostaCapitolo("T", "f")]


@pytest.mark.parametrize(
    "contenuto",
    [
        "",
        "Non so cosa rispondere",
        '{"capitoli": "niente"}',
        '{"altro": []}',
        '{"capitoli": [{"titolo": "senza frase"}]}',
    ],
)
def test_una_risposta_inutilizzabile_e_una_segmentazione_non_valida(contenuto: str) -> None:
    with pytest.raises(SegmentazioneNonValida):
        _con_contenuto(contenuto).proponi_capitoli("t")


def test_un_errore_di_rete_non_viene_trasformato_in_segmentazione_non_valida() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama irraggiungibile")

    with pytest.raises(httpx.ConnectError):
        _segmentatore(httpx.MockTransport(handler)).proponi_capitoli("t")


def test_un_errore_http_del_server_non_viene_trasformato_in_segmentazione_non_valida() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        _segmentatore(httpx.MockTransport(handler)).proponi_capitoli("t")
