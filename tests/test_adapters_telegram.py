from __future__ import annotations

import json
from datetime import date

import httpx

from trascrizione_lezioni.adapters.telegram import ClientTelegramReale
from trascrizione_lezioni.dominio import Lezione


def test_notifica_appunti_manda_un_solo_messaggio_di_testo_semplice_alla_chat_della_lezione() -> None:
    richieste: list[httpx.Request] = []

    def handler(richiesta: httpx.Request) -> httpx.Response:
        richieste.append(richiesta)
        return httpx.Response(200, json={"ok": True})

    client = ClientTelegramReale(token="TOKEN", admin_chat_id="admin", api_base_url="http://tg.test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    lezione = Lezione(id="l", materia="Fisica 1", data=date(2026, 3, 5), chat_id="fratello-1")

    client.notifica_appunti(lezione, ["Attrito <statico> & dinamico", "Lavoro"], None)

    assert len(richieste) == 1
    assert richieste[0].url.path == "/botTOKEN/sendMessage"
    corpo = json.loads(richieste[0].content)
    assert corpo["chat_id"] == "fratello-1"
    assert corpo["text"].startswith("📚 Appunti aggiornati: Fisica 1 05/03")
    assert "• Attrito <statico> & dinamico" in corpo["text"]  # nessuna interpretazione HTML
    assert "parse_mode" not in corpo


def test_notifica_appunti_include_il_link_quando_c_e() -> None:
    richieste: list[httpx.Request] = []

    def handler(richiesta: httpx.Request) -> httpx.Response:
        richieste.append(richiesta)
        return httpx.Response(200, json={"ok": True})

    client = ClientTelegramReale(token="TOKEN", admin_chat_id="admin", api_base_url="http://tg.test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    lezione = Lezione(id="l", materia="Fisica 1", data=date(2026, 3, 5), chat_id="fratello-1")

    client.notifica_appunti(lezione, ["Attrito"], "https://studio.example/capitolo/r/0")

    testo = json.loads(richieste[0].content)["text"]
    assert testo.endswith("👉 https://studio.example/capitolo/r/0")
