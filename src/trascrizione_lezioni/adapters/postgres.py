"""Repository reale su Postgres. Adapter sottile: converte tra Lezione/Registrazione e righe SQL."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import date

import psycopg

from psycopg.types.json import Jsonb

from ..dominio import (
    AppuntiCapitolo,
    Capitolo,
    CapitoloTagliato,
    Lezione,
    Registrazione,
    Stato,
)

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


@contextmanager
def scrittura(connessione: psycopg.Connection) -> Iterator[psycopg.Cursor[tuple[object, ...]]]:
    """Un cursore in una transazione: commit se va bene, rollback se fallisce, così
    un errore non lascia la connessione in una transazione abortita."""
    try:
        with connessione.cursor() as cursore:
            yield cursore
        connessione.commit()
    except BaseException:
        connessione.rollback()
        raise


class ElaborazioneInCorso(Exception):
    """Una Registrazione della Lezione è ancora in mano all'Orchestratore."""


class RepositoryPostgres:
    def __init__(self, connessione: psycopg.Connection) -> None:
        self._connessione = connessione

    def _scrittura(self) -> AbstractContextManager[psycopg.Cursor[tuple[object, ...]]]:
        return scrittura(self._connessione)

    def trova_lezione(self, materia: str, data: date) -> Lezione | None:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                "SELECT id, materia, data, chat_id, quadro_generale FROM lezioni "
                "WHERE materia = %s AND data = %s",
                (materia, data),
            )
            riga = cursore.fetchone()
        self._connessione.rollback()
        if riga is None:
            return None
        return Lezione(
            id=riga[0], materia=riga[1], data=riga[2], chat_id=riga[3], quadro_generale=riga[4]
        )

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
                    percorso_appunti, tentativi
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    lezione_id = EXCLUDED.lezione_id,
                    stato = EXCLUDED.stato,
                    percorso_audio = EXCLUDED.percorso_audio,
                    trascrizione = EXCLUDED.trascrizione,
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

    def salva_appunti(self, capitolo: Capitolo, appunti: AppuntiCapitolo) -> None:
        with self._scrittura() as cursore:
            cursore.execute(
                "UPDATE capitoli SET appunti = %s WHERE registrazione_id = %s AND posizione = %s",
                (Jsonb(appunti.a_dict()), capitolo.registrazione_id, capitolo.posizione),
            )
            if cursore.rowcount != 1:
                raise LookupError(
                    f"Capitolo {capitolo.posizione} della Registrazione "
                    f"{capitolo.registrazione_id} non trovato"
                )

    def salva_quadro_generale(self, lezione: Lezione, quadro_generale: str) -> None:
        with self._scrittura() as cursore:
            cursore.execute(
                "UPDATE lezioni SET quadro_generale = %s, aggiornato_il = now() WHERE id = %s",
                (quadro_generale, lezione.id),
            )
            if cursore.rowcount != 1:
                raise LookupError(f"Lezione {lezione.id} non trovata")

    def capitoli_della_lezione(self, lezione: Lezione) -> list[Capitolo]:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT c.registrazione_id, c.posizione, c.titolo, c.testo, c.appunti
                FROM capitoli c
                JOIN registrazioni r ON r.id = c.registrazione_id
                WHERE r.lezione_id = %s
                ORDER BY r.creato_il, r.id, c.posizione
                """,
                (lezione.id,),
            )
            righe = cursore.fetchall()
        self._connessione.rollback()
        return [
            Capitolo(
                registrazione_id,
                posizione,
                titolo,
                testo,
                AppuntiCapitolo.da_dict(appunti) if appunti is not None else None,
            )
            for registrazione_id, posizione, titolo, testo, appunti in righe
        ]

    def capitoli_con_progresso(self, lezione: Lezione) -> int:
        """Quanti Capitoli della Lezione hanno uno Stato di comprensione scelto dal fratello."""
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT count(*) FROM capitoli c
                JOIN registrazioni r ON r.id = c.registrazione_id
                WHERE r.lezione_id = %s AND c.stato_comprensione <> 'da_studiare'
                """,
                (lezione.id,),
            )
            (quanti,) = cursore.fetchone() or (0,)
        self._connessione.rollback()
        return int(quanti)

    def riavvia_elaborazione(self, lezione: Lezione) -> int:
        """Rifà da capo segmentazione, Appunti e archiviazione di una Lezione, partendo dalle
        Trascrizioni già salvate (che non si toccano). Le Registrazioni senza Trascrizione,
        ancora da trascrivere, restano dove sono. Restituisce quante ne ha riavviate.

        Attenzione: i Capitoli si ricreano, quindi lo Stato di comprensione si perde
        (vedi `capitoli_con_progresso`). Solleva ElaborazioneInCorso se l'Orchestratore sta
        ancora lavorando su una Registrazione della Lezione."""
        with scrittura(self._connessione) as cursore:
            # Il blocco delle righe impedisce all'Orchestratore di avanzarle mentre si controlla.
            cursore.execute(
                """
                SELECT id, stato FROM registrazioni
                WHERE lezione_id = %s AND trascrizione IS NOT NULL
                ORDER BY creato_il FOR UPDATE
                """,
                (lezione.id,),
            )
            in_lavorazione = [
                str(id_)
                for id_, stato in cursore.fetchall()
                if stato in ("trascritta", "segmentata", "elaborata", "archiviata")
            ]
            if in_lavorazione:
                raise ElaborazioneInCorso(
                    "Registrazioni ancora in lavorazione: " + ", ".join(in_lavorazione)
                )
            cursore.execute(
                """
                DELETE FROM capitoli WHERE registrazione_id IN (
                    SELECT id FROM registrazioni WHERE lezione_id = %s AND trascrizione IS NOT NULL
                )
                """,
                (lezione.id,),
            )
            cursore.execute(
                """
                UPDATE registrazioni
                SET stato = 'trascritta', tentativi = 0, percorso_appunti = NULL,
                    aggiornato_il = now()
                WHERE lezione_id = %s AND trascrizione IS NOT NULL
                """,
                (lezione.id,),
            )
            riavviate = cursore.rowcount
            if riavviate:
                cursore.execute(
                    "UPDATE lezioni SET quadro_generale = NULL, aggiornato_il = now() WHERE id = %s",
                    (lezione.id,),
                )
        return riavviate

    def registrazioni_da_processare(self) -> list[Registrazione]:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT r.id, r.stato, r.percorso_audio, r.trascrizione,
                       r.percorso_appunti, r.tentativi,
                       l.id, l.materia, l.data, l.chat_id, l.quadro_generale
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
        str, str, str, str | None, str | None, int, str, str, date, str, str | None
    ],
) -> Registrazione:
    (
        id_,
        stato,
        percorso_audio,
        trascrizione,
        percorso_appunti,
        tentativi,
        lezione_id,
        materia,
        data_,
        chat_id,
        quadro_generale,
    ) = riga
    return Registrazione(
        id=id_,
        lezione=Lezione(
            id=lezione_id,
            materia=materia,
            data=data_,
            chat_id=chat_id,
            quadro_generale=quadro_generale,
        ),
        percorso_audio=percorso_audio,
        stato=_TESTO_A_STATO[stato],
        trascrizione=trascrizione,
        percorso_appunti=percorso_appunti,
        tentativi=tentativi,
    )
