"""Sorveglianza del Mac Mini: un timer systemd la lancia ogni 5 minuti. Controlla che i
servizi girino, che il database risponda e che nessuna Registrazione sia ferma; avvisa
l'admin su Telegram quando compare un problema e quando tutto torna a posto (non a ogni
giro); infine manda un battito a Healthchecks.io.

Il battito copre il caso che da qui non si può segnalare: se il Mac Mini è spento o senza
internet i battiti smettono di arrivare e Healthchecks avvisa da fuori. Se l'avviso su
Telegram non parte (es. container telegram-bot-api giù), il battito segnala il fallimento
e avvisa Healthchecks. Esegui con:
uv run python -m trascrizione_lezioni.sorveglianza
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv

from .adapters.postgres import RepositoryPostgres
from .adapters.telegram import API_BASE_URL_DEFAULT, ClientTelegramReale

SERVIZI = (
    "trascrizione-lezioni-bot",
    "trascrizione-lezioni-orchestratore",
    "trascrizione-lezioni-web",
)
# L'MSI può restare occupato o spento per ore (ADR 0002): sotto questa soglia non è un guasto.
SOGLIA_REGISTRAZIONE_FERMA = timedelta(hours=12)

Controllo = Callable[[], list[str]]
"""Restituisce i problemi trovati, come frasi stabili da un giro all'altro (niente orari
o contatori), così lo stesso problema non viene notificato di nuovo."""

logger = logging.getLogger(__name__)


def esegui(
    *,
    controlli: dict[str, Controllo],
    percorso_stato: Path,
    invia_admin: Callable[[str], None],
    battito: Callable[[str | None], None],
) -> list[str]:
    """Un giro di sorveglianza. `battito(None)` vuol dire tutto in ordine, `battito(testo)`
    un fallimento da segnalare da fuori. Restituisce i problemi trovati."""

    problemi = _raccogli_problemi(controlli)
    messaggio = _messaggio_per_admin(problemi, _leggi_stato(percorso_stato))
    if messaggio is None:
        battito(None)
        return problemi

    try:
        invia_admin(messaggio)
    except Exception as errore:
        # Lo stato non si aggiorna: al prossimo giro si riprova a notificare.
        logger.exception("Avviso su Telegram non riuscito")
        battito("\n".join([*problemi, f"Avviso su Telegram non riuscito: {errore}"]))
        return problemi

    _scrivi_stato(percorso_stato, problemi)
    battito(None)
    return problemi


def _raccogli_problemi(controlli: dict[str, Controllo]) -> list[str]:
    problemi: list[str] = []
    for nome, controllo in controlli.items():
        try:
            problemi.extend(controllo())
        except Exception as errore:
            problemi.append(f"Controllo «{nome}» fallito: {errore}")
    return problemi


def _messaggio_per_admin(problemi: list[str], precedenti: list[str]) -> str | None:
    if sorted(problemi) == sorted(precedenti):
        return None
    if not problemi:
        return "✅ Mac Mini: tutto di nuovo a posto."
    return "⚠️ Mac Mini, qualcosa non va:\n" + "\n".join(f"• {p}" for p in problemi)


def _leggi_stato(percorso: Path) -> list[str]:
    try:
        return list(json.loads(percorso.read_text()))
    except (OSError, ValueError, TypeError):
        return []


def _scrivi_stato(percorso: Path, problemi: list[str]) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(problemi, ensure_ascii=False))


def controlla_servizi() -> list[str]:
    return [
        f"Il servizio {servizio} non è attivo"
        for servizio in SERVIZI
        if subprocess.run(["systemctl", "--user", "is-active", "--quiet", servizio]).returncode != 0
    ]


def controlla_database(database_url: str) -> list[str]:
    try:
        connessione = psycopg.connect(database_url, connect_timeout=10)
    except psycopg.OperationalError:
        return ["Il database non risponde"]
    with connessione:
        ferme = RepositoryPostgres(connessione).registrazioni_ferme(SOGLIA_REGISTRAZIONE_FERMA)
    ore = int(SOGLIA_REGISTRAZIONE_FERMA.total_seconds() // 3600)
    return [
        f"Registrazione di {r.lezione.materia} del {r.lezione.data.isoformat()} ferma "
        f"allo stato «{r.stato.name.lower()}» da più di {ore} ore"
        for r in ferme
    ]


def battito_healthchecks(url: str | None) -> Callable[[str | None], None]:
    def battito(fallimento: str | None) -> None:
        if url is None:
            return
        try:
            if fallimento is None:
                httpx.get(url, timeout=10.0)
            else:
                httpx.post(f"{url}/fail", content=fallimento.encode(), timeout=10.0)
        except httpx.HTTPError:
            # Senza internet il battito non parte: è proprio il caso che Healthchecks vede da fuori.
            logger.warning("Battito a Healthchecks non riuscito")

    return battito


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx scrive l'URL di ogni richiesta, e qui gli URL contengono token e link di ping.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    database_url = _leggi_env_obbligatoria("DATABASE_URL")
    client_telegram = ClientTelegramReale(
        token=_leggi_env_obbligatoria("TELEGRAM_BOT_TOKEN"),
        admin_chat_id=_leggi_env_obbligatoria("TELEGRAM_ADMIN_CHAT_ID"),
        api_base_url=os.environ.get("TELEGRAM_API_BASE_URL") or API_BASE_URL_DEFAULT,
    )
    ping_url = os.environ.get("HEALTHCHECKS_PING_URL") or None
    if ping_url is None:
        logger.warning("HEALTHCHECKS_PING_URL non impostata: nessun battito, i blackout non verranno segnalati")
    cartella_stato = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")

    problemi = esegui(
        controlli={
            "servizi": controlla_servizi,
            "database": lambda: controlla_database(database_url),
        },
        percorso_stato=cartella_stato / "trascrizione-lezioni" / "sorveglianza.json",
        invia_admin=client_telegram.invia_admin,
        battito=battito_healthchecks(ping_url.rstrip("/") if ping_url else None),
    )
    logger.info("Sorveglianza: %s", "; ".join(problemi) if problemi else "tutto in ordine")


def _leggi_env_obbligatoria(nome: str) -> str:
    valore = os.environ.get(nome)
    if not valore:
        raise RuntimeError(f"Variabile d'ambiente {nome} mancante o vuota (vedi .env.example)")
    return valore


if __name__ == "__main__":
    main()
