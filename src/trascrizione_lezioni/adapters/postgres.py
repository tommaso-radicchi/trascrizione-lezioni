"""Repository reale su Postgres. Adapter sottile: converte tra Lezione e righe SQL."""

from __future__ import annotations

from datetime import date

import psycopg

from ..dominio import Lezione, Stato

_STATO_A_TESTO: dict[Stato, str] = {
    Stato.RICEVUTA: "ricevuta",
    Stato.TRASCRITTA: "trascritta",
    Stato.ELABORATA: "elaborata",
    Stato.ARCHIVIATA: "archiviata",
    Stato.NOTIFICATA: "notificata",
    Stato.ERRORE: "errore",
}
_TESTO_A_STATO: dict[str, Stato] = {testo: stato for stato, testo in _STATO_A_TESTO.items()}


class RepositoryPostgres:
    def __init__(self, connessione: psycopg.Connection) -> None:
        self._connessione = connessione

    def salva(self, lezione: Lezione) -> None:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                INSERT INTO lezioni (
                    id, materia, data, stato, percorso_audio, chat_id, trascrizione,
                    appunti_markdown, percorso_appunti, tentativi
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    materia = EXCLUDED.materia,
                    data = EXCLUDED.data,
                    stato = EXCLUDED.stato,
                    percorso_audio = EXCLUDED.percorso_audio,
                    chat_id = EXCLUDED.chat_id,
                    trascrizione = EXCLUDED.trascrizione,
                    appunti_markdown = EXCLUDED.appunti_markdown,
                    percorso_appunti = EXCLUDED.percorso_appunti,
                    tentativi = EXCLUDED.tentativi,
                    aggiornato_il = now()
                """,
                (
                    lezione.id,
                    lezione.materia,
                    lezione.data,
                    _STATO_A_TESTO[lezione.stato],
                    lezione.percorso_audio,
                    lezione.chat_id,
                    lezione.trascrizione,
                    lezione.appunti_markdown,
                    lezione.percorso_appunti,
                    lezione.tentativi,
                ),
            )
        self._connessione.commit()

    def da_processare(self) -> list[Lezione]:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT id, materia, data, stato, percorso_audio, chat_id, trascrizione,
                       appunti_markdown, percorso_appunti, tentativi
                FROM lezioni
                WHERE stato NOT IN ('notificata', 'errore')
                ORDER BY creato_il
                """
            )
            righe = cursore.fetchall()
        return [_riga_a_lezione(riga) for riga in righe]


def _riga_a_lezione(
    riga: tuple[str, str, date, str, str, str, str | None, str | None, str | None, int],
) -> Lezione:
    (
        id_,
        materia,
        data_,
        stato,
        percorso_audio,
        chat_id,
        trascrizione,
        appunti_markdown,
        percorso_appunti,
        tentativi,
    ) = riga
    return Lezione(
        id=id_,
        materia=materia,
        data=data_,
        percorso_audio=percorso_audio,
        chat_id=chat_id,
        stato=_TESTO_A_STATO[stato],
        trascrizione=trascrizione,
        appunti_markdown=appunti_markdown,
        percorso_appunti=percorso_appunti,
        tentativi=tentativi,
    )
