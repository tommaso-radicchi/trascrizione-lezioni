from __future__ import annotations

import httpx

from trascrizione_lezioni.adapters.msi import (
    ClientTrascrizioneMsi,
    ControlloGpuMsi,
    costruisci_pacchetto_wol,
)


def test_costruisci_pacchetto_wol_ha_la_forma_attesa() -> None:
    pacchetto = costruisci_pacchetto_wol("D8:43:AE:87:4A:2B")

    assert len(pacchetto) == 102
    assert pacchetto[:6] == b"\xff" * 6
    mac_atteso = bytes.fromhex("D843AE874A2B")
    for i in range(16):
        inizio = 6 + i * 6
        assert pacchetto[inizio : inizio + 6] == mac_atteso


def test_gpu_libera_quando_sotto_le_soglie() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"utilizzo_percento": 0.0, "vram_libera_mb": 5000.0})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    controllo = ControlloGpuMsi(
        base_url="http://msi.test", mac_address="D8:43:AE:87:4A:2B", client=client
    )

    assert controllo.libera() is True


def test_gpu_occupata_quando_sopra_le_soglie() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"utilizzo_percento": 80.0, "vram_libera_mb": 200.0})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    controllo = ControlloGpuMsi(
        base_url="http://msi.test", mac_address="D8:43:AE:87:4A:2B", client=client
    )

    assert controllo.libera() is False


def test_msi_irraggiungibile_invia_wol_e_risulta_occupata() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("MSI addormentato", request=richiesta)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mac_svegliati: list[str] = []
    controllo = ControlloGpuMsi(
        base_url="http://msi.test",
        mac_address="D8:43:AE:87:4A:2B",
        client=client,
        invia_wol_fn=mac_svegliati.append,
    )

    assert controllo.libera() is False
    assert mac_svegliati == ["D8:43:AE:87:4A:2B"]


def test_msi_irraggiungibile_non_reinvia_wol_durante_il_cooldown() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("MSI addormentato", request=richiesta)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mac_svegliati: list[str] = []
    controllo = ControlloGpuMsi(
        base_url="http://msi.test",
        mac_address="D8:43:AE:87:4A:2B",
        client=client,
        invia_wol_fn=mac_svegliati.append,
        cooldown_wol_secondi=999.0,
    )

    controllo.libera()
    controllo.libera()

    assert mac_svegliati == ["D8:43:AE:87:4A:2B"]


def test_dopo_troppi_tentativi_di_sveglia_falliti_notifica_una_volta() -> None:
    def handler(richiesta: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("MSI addormentato", request=richiesta)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifiche: list[str] = []
    controllo = ControlloGpuMsi(
        base_url="http://msi.test",
        mac_address="D8:43:AE:87:4A:2B",
        client=client,
        invia_wol_fn=lambda mac: None,
        cooldown_wol_secondi=0.0,
        tentativi_sveglia_massimi=3,
        notifica_irraggiungibile_fn=notifiche.append,
    )

    for _ in range(5):
        controllo.libera()

    assert len(notifiche) == 1


def test_dopo_la_notifica_se_msi_torna_libera_una_nuova_assenza_notifica_di_nuovo() -> None:
    stato = {"libera": False}

    def handler(richiesta: httpx.Request) -> httpx.Response:
        if stato["libera"]:
            return httpx.Response(200, json={"utilizzo_percento": 0.0, "vram_libera_mb": 5000.0})
        raise httpx.ConnectError("MSI addormentato", request=richiesta)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifiche: list[str] = []
    controllo = ControlloGpuMsi(
        base_url="http://msi.test",
        mac_address="D8:43:AE:87:4A:2B",
        client=client,
        invia_wol_fn=lambda mac: None,
        cooldown_wol_secondi=0.0,
        tentativi_sveglia_massimi=2,
        notifica_irraggiungibile_fn=notifiche.append,
    )

    controllo.libera()
    controllo.libera()
    assert len(notifiche) == 1

    stato["libera"] = True
    controllo.libera()

    stato["libera"] = False
    controllo.libera()
    controllo.libera()
    assert len(notifiche) == 2


def test_dopo_un_ritorno_online_una_nuova_assenza_invia_subito_un_nuovo_wol() -> None:
    stato = {"libera": False}

    def handler(richiesta: httpx.Request) -> httpx.Response:
        if stato["libera"]:
            return httpx.Response(200, json={"utilizzo_percento": 0.0, "vram_libera_mb": 5000.0})
        raise httpx.ConnectError("MSI addormentato", request=richiesta)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mac_svegliati: list[str] = []
    controllo = ControlloGpuMsi(
        base_url="http://msi.test",
        mac_address="D8:43:AE:87:4A:2B",
        client=client,
        invia_wol_fn=mac_svegliati.append,
        cooldown_wol_secondi=999.0,
    )

    controllo.libera()
    assert mac_svegliati == ["D8:43:AE:87:4A:2B"]

    stato["libera"] = True
    controllo.libera()

    stato["libera"] = False
    controllo.libera()

    assert mac_svegliati == ["D8:43:AE:87:4A:2B", "D8:43:AE:87:4A:2B"]


def test_client_trascrizione_msi_carica_laudio_e_restituisce_il_testo(tmp_path: object) -> None:
    from pathlib import Path

    file_audio = Path(str(tmp_path)) / "lezione.oga"
    file_audio.write_bytes(b"audio finto")

    def handler(richiesta: httpx.Request) -> httpx.Response:
        assert richiesta.url.path == "/trascrivi"
        return httpx.Response(200, json={"testo": "questo è il testo trascritto"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client_trascrizione = ClientTrascrizioneMsi(base_url="http://msi.test", client=client)

    testo = client_trascrizione.trascrivi(str(file_audio))

    assert testo == "questo è il testo trascritto"
