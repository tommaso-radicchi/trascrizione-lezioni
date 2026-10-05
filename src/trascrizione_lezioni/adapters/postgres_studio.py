"""Lettura per il sito di studio su Postgres (vedi studio.py). Adapter sottile: si
limita a leggere Lezioni e Capitoli già elaborati e a salvare lo Stato di comprensione."""

from __future__ import annotations

import psycopg

from ..dominio import AppuntiCapitolo, StatoComprensione
from ..studio import CapitoloConAppunti, CapitoloStudio, DettaglioCapitolo, LezioneStudio
from .postgres import scrittura


class LetturaStudioPostgres:
    def __init__(self, connessione: psycopg.Connection) -> None:
        self._connessione = connessione

    def lezioni(self) -> list[LezioneStudio]:
        return self._carica_lezioni(None)

    def _carica_lezioni(self, lezione_id: str | None) -> list[LezioneStudio]:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT l.id, l.materia, l.data, l.quadro_generale,
                       c.registrazione_id, c.posizione, c.titolo, c.stato_comprensione,
                       c.aperto_il IS NULL
                FROM lezioni l
                JOIN registrazioni r ON r.lezione_id = l.id
                JOIN capitoli c ON c.registrazione_id = r.id
                WHERE c.appunti IS NOT NULL AND (%s::text IS NULL OR l.id = %s)
                ORDER BY l.data, l.id, r.creato_il, r.id, c.posizione
                """,
                (lezione_id, lezione_id),
            )
            righe = cursore.fetchall()
        self._connessione.rollback()

        lezioni: list[LezioneStudio] = []
        for id_, materia, data, quadro, registrazione_id, posizione, titolo, stato, nuovo in righe:
            if not lezioni or lezioni[-1].id != id_:
                lezioni.append(LezioneStudio(id_, materia, data, quadro, capitoli=[]))
            capitoli = lezioni[-1].capitoli
            capitoli.append(
                CapitoloStudio(
                    registrazione_id,
                    posizione,
                    titolo,
                    StatoComprensione(stato),
                    len(capitoli) + 1,
                    nuovo=bool(nuovo),
                )
            )
        return lezioni

    def dettaglio_capitolo(
        self, registrazione_id: str, posizione: int
    ) -> DettaglioCapitolo | None:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT c.testo, c.appunti, r.lezione_id
                FROM capitoli c
                JOIN registrazioni r ON r.id = c.registrazione_id
                WHERE c.registrazione_id = %s AND c.posizione = %s AND c.appunti IS NOT NULL
                """,
                (registrazione_id, posizione),
            )
            riga = cursore.fetchone()
        self._connessione.rollback()
        if riga is None:
            return None
        testo, appunti, lezione_id = riga

        # Solo la Lezione di questo Capitolo: servono i suoi Capitoli per linea del tempo e navigazione.
        for lezione in self._carica_lezioni(lezione_id):
            for capitolo in lezione.capitoli:
                if capitolo.registrazione_id == registrazione_id and capitolo.posizione == posizione:
                    return DettaglioCapitolo(lezione, capitolo, testo, AppuntiCapitolo.da_dict(appunti))
        return None

    def appunti_della_materia(self, materia: str) -> list[CapitoloConAppunti]:
        with self._connessione.cursor() as cursore:
            cursore.execute(
                """
                SELECT l.id, l.data, c.registrazione_id, c.posizione, c.titolo,
                       c.stato_comprensione, c.aperto_il IS NULL, c.appunti
                FROM lezioni l
                JOIN registrazioni r ON r.lezione_id = l.id
                JOIN capitoli c ON c.registrazione_id = r.id
                WHERE l.materia = %s AND c.appunti IS NOT NULL
                ORDER BY l.data, l.id, r.creato_il, r.id, c.posizione
                """,
                (materia,),
            )
            righe = cursore.fetchall()
        self._connessione.rollback()

        voci: list[CapitoloConAppunti] = []
        lezione_corrente, numero = None, 0
        for lezione_id, data, registrazione_id, posizione, titolo, stato, nuovo, appunti in righe:
            numero = numero + 1 if lezione_id == lezione_corrente else 1
            lezione_corrente = lezione_id
            capitolo = CapitoloStudio(
                registrazione_id, posizione, titolo, StatoComprensione(stato), numero, nuovo=bool(nuovo)
            )
            voci.append(CapitoloConAppunti(data, capitolo, AppuntiCapitolo.da_dict(appunti)))
        return voci

    def segna_aperto(self, registrazione_id: str, posizione: int) -> None:
        with scrittura(self._connessione) as cursore:
            cursore.execute(
                """
                UPDATE capitoli SET aperto_il = now()
                WHERE registrazione_id = %s AND posizione = %s AND aperto_il IS NULL
                """,
                (registrazione_id, posizione),
            )

    def imposta_stato(
        self, registrazione_id: str, posizione: int, stato: StatoComprensione
    ) -> bool:
        with scrittura(self._connessione) as cursore:
            cursore.execute(
                """
                UPDATE capitoli SET stato_comprensione = %s
                WHERE registrazione_id = %s AND posizione = %s AND appunti IS NOT NULL
                """,
                (stato.value, registrazione_id, posizione),
            )
            return cursore.rowcount == 1
