"""Rielabora una Lezione con la pipeline attuale, dalle Trascrizioni già salvate.

Serve dopo un cambio di formato o di prompt, o per una Lezione elaborata dal flusso vecchio.
L'Orchestratore in esecuzione riprende poi le Registrazioni riavviate e rifà segmentazione,
Appunti, archiviazione e notifica. Esegui con:
uv run python -m trascrizione_lezioni.rielabora "Matematica Generale" 2026-09-21 [--forza]

Si rifiuta se la Lezione ha Registrazioni ancora in lavorazione, o Capitoli con uno Stato di
comprensione già scelto (i Capitoli si ricreano e lo stato si perderebbe): con --forza va avanti.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import psycopg
from dotenv import load_dotenv

from .adapters.postgres import ElaborazioneInCorso, RepositoryPostgres


def main(argomenti: list[str]) -> int:
    forza = "--forza" in argomenti
    argomenti = [a for a in argomenti if a != "--forza"]
    if len(argomenti) != 2:
        print(
            'Uso: python -m trascrizione_lezioni.rielabora "<Materia>" <AAAA-MM-GG> [--forza]',
            file=sys.stderr,
        )
        return 2
    materia = argomenti[0]
    try:
        giorno = date.fromisoformat(argomenti[1])
    except ValueError:
        print(f"Data non valida: {argomenti[1]!r} (formato AAAA-MM-GG)", file=sys.stderr)
        return 2

    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL mancante o vuota (vedi .env.example)", file=sys.stderr)
        return 1

    with psycopg.connect(database_url) as connessione:
        repository = RepositoryPostgres(connessione)
        lezione = repository.trova_lezione(materia, giorno)
        if lezione is None:
            print(f"Nessuna Lezione di {materia} del {giorno.isoformat()}", file=sys.stderr)
            return 1
        con_progresso = repository.capitoli_con_progresso(lezione)
        if con_progresso and not forza:
            print(
                f"{con_progresso} Capitoli hanno già uno stato di comprensione: rielaborando "
                "si perderebbe. Usa --forza per procedere comunque.",
                file=sys.stderr,
            )
            return 1
        try:
            riavviate = repository.riavvia_elaborazione(lezione)
        except ElaborazioneInCorso as errore:
            print(f"{errore}. Riprova quando l'Orchestratore ha finito.", file=sys.stderr)
            return 1

    print(f"{materia} {giorno.isoformat()}: {riavviate} Registrazioni riavviate.")
    if riavviate:
        print("L'Orchestratore le riprende al prossimo giro (circa 30 secondi).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
