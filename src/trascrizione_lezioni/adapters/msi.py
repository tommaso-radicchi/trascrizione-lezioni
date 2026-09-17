"""Adapter reali verso l'MSI: controllo GPU (con sveglia Wake-on-LAN) e
trascrizione via il server faster-whisper nativo (vedi msi_server/, ADR 0002,
issue #4). Adapter sottile: non coperto dal seam principale di test."""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

SOGLIA_UTILIZZO_PERCENTO = 10.0
SOGLIA_VRAM_LIBERA_MB = 2000.0
COOLDOWN_WOL_SECONDI = 60.0


def costruisci_pacchetto_wol(mac_address: str) -> bytes:
    mac_pulito = mac_address.replace(":", "").replace("-", "")
    if len(mac_pulito) != 12:
        raise ValueError(f"MAC address non valido: {mac_address}")
    try:
        mac_grezzo = bytes.fromhex(mac_pulito)
    except ValueError:
        raise ValueError(f"MAC address non valido: {mac_address}") from None
    return b"\xff" * 6 + mac_grezzo * 16


def invia_wol(mac_address: str, indirizzo_broadcast: str = "255.255.255.255", porta: int = 9) -> None:
    pacchetto = costruisci_pacchetto_wol(mac_address)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(pacchetto, (indirizzo_broadcast, porta))


class ControlloGpuMsi:
    def __init__(
        self,
        *,
        base_url: str,
        mac_address: str,
        client: httpx.Client | None = None,
        soglia_utilizzo_percento: float = SOGLIA_UTILIZZO_PERCENTO,
        soglia_vram_libera_mb: float = SOGLIA_VRAM_LIBERA_MB,
        cooldown_wol_secondi: float = COOLDOWN_WOL_SECONDI,
        invia_wol_fn: Callable[[str], None] = invia_wol,
    ) -> None:
        self._base_url = base_url
        self._mac_address = mac_address
        self._client = client or httpx.Client(timeout=5.0)
        self._soglia_utilizzo_percento = soglia_utilizzo_percento
        self._soglia_vram_libera_mb = soglia_vram_libera_mb
        self._cooldown_wol_secondi = cooldown_wol_secondi
        self._invia_wol_fn = invia_wol_fn
        self._ultimo_wol: float | None = None

    def libera(self) -> bool:
        try:
            risposta = self._client.get(f"{self._base_url}/stato-gpu")
            risposta.raise_for_status()
            dati = risposta.json()
            return bool(
                dati["utilizzo_percento"] < self._soglia_utilizzo_percento
                and dati["vram_libera_mb"] > self._soglia_vram_libera_mb
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            self._sveglia_se_serve()
            return False

    def _sveglia_se_serve(self) -> None:
        ora = time.monotonic()
        if self._ultimo_wol is not None and ora - self._ultimo_wol < self._cooldown_wol_secondi:
            return
        logger.info("MSI non raggiungibile, invio Wake-on-LAN")
        self._invia_wol_fn(self._mac_address)
        self._ultimo_wol = ora


class ClientTrascrizioneMsi:
    def __init__(self, *, base_url: str, client: httpx.Client | None = None) -> None:
        self._base_url = base_url
        self._client = client or httpx.Client(timeout=600.0)

    def trascrivi(self, percorso_audio: str) -> str:
        with Path(percorso_audio).open("rb") as file_audio:
            risposta = self._client.post(
                f"{self._base_url}/trascrivi",
                files={"file": (Path(percorso_audio).name, file_audio)},
            )
        risposta.raise_for_status()
        return str(risposta.json()["testo"])
