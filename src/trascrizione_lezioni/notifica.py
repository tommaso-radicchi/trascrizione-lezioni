"""Il testo della notifica Telegram: Telegram è solo un avviso, gli Appunti si
leggono altrove (vedi CONTEXT.md e ADR 0003). Testo semplice, senza formattazione,
così i titoli generati dal LLM non possono rompere il messaggio."""

from __future__ import annotations

from .dominio import Lezione


def componi_notifica(
    lezione: Lezione, titoli_nuovi: list[str], link: str | None = None
) -> str:
    intestazione = (
        f"📚 Appunti aggiornati: {lezione.materia} {lezione.data.strftime('%d/%m')}"
    )
    testo = intestazione
    if titoli_nuovi:
        conteggio = (
            "1 nuovo argomento"
            if len(titoli_nuovi) == 1
            else f"{len(titoli_nuovi)} nuovi argomenti"
        )
        elenco = "\n".join(f"• {titolo}" for titolo in titoli_nuovi)
        testo = f"{intestazione}\n\n{conteggio}:\n{elenco}"
    if link:
        testo += f"\n\n👉 {link}"
    return testo
