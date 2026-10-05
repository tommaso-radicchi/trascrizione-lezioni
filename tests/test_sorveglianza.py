from __future__ import annotations

from pathlib import Path

import pytest

from trascrizione_lezioni.sorveglianza import Controllo, esegui


class Giro:
    """Raccoglie gli avvisi e i battiti di più giri di sorveglianza sullo stesso stato."""

    def __init__(self, cartella: Path) -> None:
        self.percorso_stato = cartella / "stato" / "sorveglianza.json"
        self.avvisi: list[str] = []
        self.battiti: list[str | None] = []
        self.telegram_giu = False

    def esegui(self, *problemi: str, controlli: dict[str, Controllo] | None = None) -> list[str]:
        return esegui(
            controlli=controlli or {"finto": lambda: list(problemi)},
            percorso_stato=self.percorso_stato,
            invia_admin=self._invia_admin,
            battito=self.battiti.append,
        )

    def _invia_admin(self, testo: str) -> None:
        if self.telegram_giu:
            raise ConnectionError("telegram-bot-api non risponde")
        self.avvisi.append(testo)


@pytest.fixture
def giro(tmp_path: Path) -> Giro:
    return Giro(tmp_path)


def test_se_va_tutto_bene_non_avvisa_e_batte_ok(giro: Giro) -> None:
    giro.esegui()

    assert giro.avvisi == []
    assert giro.battiti == [None]


def test_un_problema_nuovo_viene_notificato_una_volta_sola(giro: Giro) -> None:
    giro.esegui("Il database non risponde")
    giro.esegui("Il database non risponde")

    assert len(giro.avvisi) == 1
    assert "Il database non risponde" in giro.avvisi[0]
    assert giro.battiti == [None, None]


def test_quando_cambiano_i_problemi_avvisa_di_nuovo(giro: Giro) -> None:
    giro.esegui("Il database non risponde")
    giro.esegui("Il database non risponde", "Il servizio x non è attivo")

    assert len(giro.avvisi) == 2
    assert "Il servizio x non è attivo" in giro.avvisi[1]


def test_quando_tutto_torna_a_posto_lo_dice(giro: Giro) -> None:
    giro.esegui("Il database non risponde")
    giro.esegui()
    giro.esegui()

    assert len(giro.avvisi) == 2
    assert "tutto di nuovo a posto" in giro.avvisi[1]


def test_se_telegram_non_risponde_lo_segnala_col_battito_e_riprova_al_giro_dopo(
    giro: Giro,
) -> None:
    giro.telegram_giu = True
    giro.esegui("Il database non risponde")

    fallimento = giro.battiti[0]
    assert fallimento is not None
    assert "Il database non risponde" in fallimento
    assert "Telegram non riuscito" in fallimento

    giro.telegram_giu = False
    giro.esegui("Il database non risponde")

    assert len(giro.avvisi) == 1
    assert giro.battiti[1] is None


def test_un_controllo_che_esplode_diventa_un_problema(giro: Giro) -> None:
    def esplode() -> list[str]:
        raise RuntimeError("systemctl assente")

    problemi = giro.esegui(controlli={"servizi": esplode, "ok": lambda: []})

    assert problemi == ["Controllo «servizi» fallito: systemctl assente"]
    assert len(giro.avvisi) == 1


def test_uno_stato_illeggibile_conta_come_nessun_problema_precedente(giro: Giro) -> None:
    giro.percorso_stato.parent.mkdir(parents=True)
    giro.percorso_stato.write_text("non è json")

    giro.esegui("Il database non risponde")

    assert len(giro.avvisi) == 1
