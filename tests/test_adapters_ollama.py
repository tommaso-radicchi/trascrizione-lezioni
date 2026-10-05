from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from trascrizione_lezioni.adapters.ollama import ClientAppuntiOllama
from trascrizione_lezioni.dominio import AppuntiCapitolo, Domanda, Termine

RISPOSTA_CAPITOLO = {
    "riassunto": "Si introduce l'attrito.",
    "punti_chiave": ["attrito statico", "attrito dinamico"],
    "termini": [{"termine": "Attrito", "definizione": "Forza che si oppone al moto relativo."}],
    "da_ripassare": ["La differenza tra i due attriti"],
    "domande": [{"domanda": "Che cos'è l'attrito?", "risposta": "Una forza resistente."}],
}


def _adapter(handler: httpx.MockTransport | object) -> ClientAppuntiOllama:
    client = httpx.Client(transport=handler)  # type: ignore[arg-type]
    return ClientAppuntiOllama(base_url="http://mac.test:11434", modello="test-model", client=client)


def _adapter_con_contenuto(contenuto: str, **extra: object) -> ClientAppuntiOllama:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": contenuto}, **extra})

    return _adapter(httpx.MockTransport(handler))


def test_genera_appunti_capitolo_manda_titolo_e_testo_e_restituisce_appunti_strutturati() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        assert richiesta.url.path == "/api/chat"
        corpo = json.loads(richiesta.content)
        assert corpo["format"]["type"] == "object"
        assert "domande" in corpo["format"]["required"]
        assert corpo["options"]["num_ctx"] == 32768
        assert "temperature" not in corpo["options"]  # per gli appunti si lascia il default
        utente = corpo["messages"][1]["content"]
        assert "Fisica 1" in utente
        assert "Titolo del capitolo: Attrito" in utente
        assert "il testo del capitolo sull'attrito" in utente
        return httpx.Response(200, json={"message": {"content": json.dumps(RISPOSTA_CAPITOLO)}})

    appunti = _adapter(httpx.MockTransport(handler)).genera_appunti_capitolo(
        "Attrito", "il testo del capitolo sull'attrito", "Fisica 1"
    )

    assert appunti == AppuntiCapitolo(
        riassunto="Si introduce l'attrito.",
        punti_chiave=["attrito statico", "attrito dinamico"],
        termini=[Termine("Attrito", "Forza che si oppone al moto relativo.")],
        da_ripassare=["La differenza tra i due attriti"],
        domande=[Domanda("Che cos'è l'attrito?", "Una forza resistente.")],
    )


def test_le_liste_vuote_sono_valide() -> None:
    contenuto = json.dumps(
        {"riassunto": "R.", "punti_chiave": ["p"], "termini": [], "da_ripassare": [], "domande": []}
    )

    appunti = _adapter_con_contenuto(contenuto).genera_appunti_capitolo("T", "t", "Fisica 1")

    assert appunti == AppuntiCapitolo(riassunto="R.", punti_chiave=["p"])


def test_tollera_testo_e_code_fence_attorno_al_json() -> None:
    contenuto = f"Ecco gli appunti:\n```json\n{json.dumps(RISPOSTA_CAPITOLO)}\n```"

    appunti = _adapter_con_contenuto(contenuto).genera_appunti_capitolo("T", "t", "Fisica 1")

    assert appunti.riassunto == "Si introduce l'attrito."


def test_tollera_backslash_latex_non_validi_nel_json() -> None:
    contenuto = (
        '{"riassunto": "Insieme mondo $\\Omega$.", "punti_chiave": ["A \\cup B"], '
        '"termini": [], "da_ripassare": [], "domande": []}'
    )

    appunti = _adapter_con_contenuto(contenuto).genera_appunti_capitolo("T", "t", "Fisica 1")

    assert "$\\Omega$" in appunti.riassunto
    assert appunti.punti_chiave == ["A \\cup B"]


def test_risposta_vuota_solleva_errore_esplicito() -> None:
    adapter = _adapter_con_contenuto("", done_reason="length")

    with pytest.raises(ValueError, match="risposta vuota.*length"):
        adapter.genera_appunti_capitolo("T", "t", "Fisica 1")


def test_risposta_senza_json_solleva_errore_esplicito() -> None:
    with pytest.raises(ValueError, match="non contiene JSON"):
        _adapter_con_contenuto("Non so cosa rispondere").genera_appunti_capitolo("T", "t", "F")


def test_risposta_senza_riassunto_solleva_errore() -> None:
    with pytest.raises(ValueError, match="Appunti"):
        _adapter_con_contenuto('{"punti_chiave": ["a"]}').genera_appunti_capitolo("T", "t", "F")


def test_genera_quadro_generale_manda_titoli_e_riassunti() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        corpo = json.loads(richiesta.content)
        assert corpo["format"]["required"] == ["quadro_generale"]
        utente = corpo["messages"][1]["content"]
        assert "Materia: Fisica 1" in utente
        assert "05/03/2026" in utente
        assert "1. Attrito: Si introduce l'attrito." in utente
        assert "2. Lavoro: Si definisce il lavoro." in utente
        return httpx.Response(
            200, json={"message": {"content": '{"quadro_generale": " Una lezione su forze e lavoro. "}'}}
        )

    quadro = _adapter(httpx.MockTransport(handler)).genera_quadro_generale(
        "Fisica 1",
        date(2026, 3, 5),
        [("Attrito", "Si introduce l'attrito."), ("Lavoro", "Si definisce il lavoro.")],
    )

    assert quadro == "Una lezione su forze e lavoro."


def test_un_quadro_generale_vuoto_solleva_errore() -> None:
    with pytest.raises(ValueError, match="quadro generale"):
        _adapter_con_contenuto('{"quadro_generale": "  "}').genera_quadro_generale(
            "Fisica 1", date(2026, 3, 5), [("A", "b")]
        )
