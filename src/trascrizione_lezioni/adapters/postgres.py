"""Repository reale su Postgres. Adapter sottile: converte tra Lezione/Registrazione e righe SQL."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import psycopg

from ..dominio import Capitolo, Lezione, Registrazione, Stato, CapitoloTagliato

_STATO_A_TESTO: dict[Stato, str] = {
    Stato.RICEVUTA: "ricevuta",
    Stato.TRASCRITTA: "trascritta",
    Stato.SEGMENTATA: "segmentata",
    Stato.ELABORATA: "elaborata",
    Stato.ARCHIVIATA: "archiviata",
    Stato.NOTIFICATA: "notificata",
    Stato.ERRORE: "errore",
}
_TESTO_A_STATO: dict[str, Stato] = {testo: stato for stato, testo in _STATO_A_TESTO.items()}


class RepositoryPostgres:
    def __init__(self, connessione: psycopg.Connection) -> None:
        self._connessione = connessione

    @contextmanager
    def _scrittura(self) -> Iterator[psycopg.Cursor[tuple[object, ...]]]:
        """Un cursore in una transazione: commit se va bene, rollback se fallisce, così
        un errore non lascia la connessione condivisa in una transazione abortita."""
        try:
            with self._connessione.cursor() as cursore:
                yield cursore
            self._connessione.commit()
        except BaseException:
            self._connessione.rollback()
            raise

    def trova_lezione(self, materia: str, data: date) -> Lezione | None:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                "SELECT id, materia, data, chat_id FROM lezioni WHERE materia = %s AND data = %s",
                (materia, data),
            )
            riga = cursore.fetchone()
        self._connessione.rollback()
        if riga is None:
            return None
        return Lezione(id=riga[0], materia=riga[1], data=riga[2], chat_id=riga[3])

    def salva_lezione(self, lezione: Lezione) -> None:
        with self._scrittura() as cursore:
            cursore.execute(
                """
                INSERT INTO lezioni (id, materia, data, chat_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    materia = EXCLUDED.materia,
                    data = EXCLUDED.data,
                    chat_id = EXCLUDED.chat_id,
                    aggiornato_il = now()
                """,
                (lezione.id, lezione.materia, lezione.data, lezione.chat_id),
            )

    def salva_registrazione(self, registrazione: Registrazione) -> None:
        with self._scrittura() as cursore:
            cursore.execute(
                """
                INSERT INTO registrazioni (
                    id, lezione_id, stato, percorso_audio, trascrizione,
                    appunti_markdown, percorso_appunti, tentativi
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    lezione_id = EXCLUDED.lezione_id,
                    stato = EXCLUDED.stato,
                    percorso_audio = EXCLUDED.percorso_audio,
                    trascrizione = EXCLUDED.trascrizione,
                    appunti_markdown = EXCLUDED.appunti_markdown,
                    percorso_appunti = EXCLUDED.percorso_appunti,
                    tentativi = EXCLUDED.tentativi,
                    aggiornato_il = now()
                """,
                (
                    registrazione.id,
                    registrazione.lezione.id,
                    _STATO_A_TESTO[registrazione.stato],
                    registrazione.percorso_audio,
                    registrazione.trascrizione,
                    registrazione.appunti_markdown,
                    registrazione.percorso_appunti,
                    registrazione.tentativi,
                ),
            )

    def sostituisci_capitoli(
        self, registrazione: Registrazione, capitoli: list[CapitoloTagliato]
    ) -> None:
        # Una sola transazione: o si sostituiscono tutti i Capitoli, o nessuno.
        with self._scrittura() as cursore:
            cursore.execute(
                "DELETE FROM capitoli WHERE registrazione_id = %s", (registrazione.id,)
            )
            cursore.executemany(
                """
                INSERT INTO capitoli (registrazione_id, posizione, titolo, testo)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (registrazione.id, posizione, capitolo.titolo, capitolo.testo)
                    for posizione, capitolo in enumerate(capitoli)
                ],
            )

    def capitoli_della_lezione(self, lezione: Lezione) -> list[Capitolo]:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT c.registrazione_id, c.posizione, c.titolo, c.testo
                FROM capitoli c
                JOIN registrazioni r ON r.id = c.registrazione_id
                WHERE r.lezione_id = %s
                ORDER BY r.creato_il, r.id, c.posizione
                """,
                (lezione.id,),
            )
            righe = cursore.fetchall()
        self._connessione.rollback()
        return [Capitolo(*riga) for riga in righe]

    def registrazioni_da_processare(self) -> list[Registrazione]:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT r.id, r.stato, r.percorso_audio, r.trascrizione, r.appunti_markdown,
                       r.percorso_appunti, r.tentativi,
                       l.id, l.materia, l.data, l.chat_id
                FROM registrazioni r
                JOIN lezioni l ON l.id = r.lezione_id
                WHERE r.stato NOT IN ('notificata', 'errore')
                ORDER BY r.creato_il
                """
            )
            righe = cursore.fetchall()
        # rollback, non commit: una SELECT non ha nulla da confermare, e su una
        # connessione condivisa un commit() qui confermerebbe anche eventuali
        # scritture pendenti di un chiamante precedente che non le ha ancora
        # confermate lui stesso.
        self._connessione.rollback()
        return [_riga_a_registrazione(riga) for riga in righe]


def _riga_a_registrazione(
    riga: tuple[
        str, str, str, str | None, str | None, str | None, int, str, str, date, str
    ],
) -> Registrazione:
    (
        id_,
        stato,
        percorso_audio,
        trascrizione,
        appunti_markdown,
        percorso_appunti,
        tentativi,
        lezione_id,
        materia,
        data_,
        chat_id,
    ) = riga
    return Registrazione(
        id=id_,
        lezione=Lezione(id=lezione_id, materia=materia, data=data_, chat_id=chat_id),
        percorso_audio=percorso_audio,
        stato=_TESTO_A_STATO[stato],
        trascrizione=trascrizione,
        appunti_markdown=appunti_markdown,
        percorso_appunti=percorso_appunti,
        tentativi=tentativi,
    )
