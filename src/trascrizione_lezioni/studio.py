"""Il modello di lettura del sito di studio (vedi ADR 0003): cosa vede il fratello
di Lezioni, Capitoli e Stato di comprensione, e le aggregazioni che alimentano la
dashboard. Solo logica pura: i dati arrivano dalla porta `LetturaStudio`."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from .dominio import AppuntiCapitolo, StatoComprensione

# Ordine fisso di barra e contatori: prima ciò che è fatto, per ultimo ciò che manca.
ORDINE_STATI = (
    StatoComprensione.COMPRESO,
    StatoComprensione.IN_CORSO,
    StatoComprensione.DA_RIPASSARE,
    StatoComprensione.DA_STUDIARE,
)

ETICHETTE_STATO: dict[StatoComprensione, tuple[str, str]] = {
    StatoComprensione.DA_STUDIARE: ("Da studiare", "○"),
    StatoComprensione.IN_CORSO: ("In corso", "◐"),
    StatoComprensione.COMPRESO: ("Compreso", "●"),
    StatoComprensione.DA_RIPASSARE: ("Da ripassare", "↻"),
}


@dataclass(frozen=True)
class CapitoloStudio:
    registrazione_id: str
    posizione: int
    titolo: str
    stato: StatoComprensione
    numero: int  # posizione 1-based dentro la Lezione, come nel Markdown in archivio


@dataclass(frozen=True)
class LezioneStudio:
    id: str
    materia: str
    data: date
    quadro_generale: str | None
    capitoli: list[CapitoloStudio]


@dataclass(frozen=True)
class DettaglioCapitolo:
    lezione: LezioneStudio
    capitolo: CapitoloStudio
    testo: str
    appunti: AppuntiCapitolo


class LetturaStudio(Protocol):
    def lezioni(self) -> list[LezioneStudio]:
        """Le Lezioni con almeno un Capitolo elaborato, dalla più vecchia; i Capitoli
        senza Appunti non compaiono."""
        ...

    def dettaglio_capitolo(
        self, registrazione_id: str, posizione: int
    ) -> DettaglioCapitolo | None: ...

    def imposta_stato(
        self, registrazione_id: str, posizione: int, stato: StatoComprensione
    ) -> bool:
        """False se il Capitolo non esiste o non è ancora visibile (senza Appunti)."""
        ...


@dataclass(frozen=True)
class RiepilogoMateria:
    materia: str
    contatori: dict[StatoComprensione, int]
    totale: int
    ultima_lezione: date | None
    continua: CapitoloStudio | None


@dataclass(frozen=True)
class VoceRipasso:
    materia: str
    data: date
    capitolo: CapitoloStudio


@dataclass(frozen=True)
class SegmentoBarra:
    stato: StatoComprensione
    percentuale: float


def riepilogo_materie(
    lezioni: list[LezioneStudio], materie_correnti: list[str]
) -> list[RiepilogoMateria]:
    """Prima le Materie correnti nell'ordine del file, poi le altre con Lezioni."""
    altre = sorted({l.materia for l in lezioni} - set(materie_correnti))
    return [
        _riepilogo(materia, [l for l in lezioni if l.materia == materia])
        for materia in [*materie_correnti, *altre]
    ]


def _riepilogo(materia: str, lezioni: list[LezioneStudio]) -> RiepilogoMateria:
    cronologiche = sorted(lezioni, key=lambda lezione: lezione.data)
    capitoli = [c for lezione in cronologiche for c in lezione.capitoli]
    contatori = {stato: sum(1 for c in capitoli if c.stato is stato) for stato in ORDINE_STATI}
    return RiepilogoMateria(
        materia=materia,
        contatori=contatori,
        totale=len(capitoli),
        ultima_lezione=cronologiche[-1].data if cronologiche else None,
        continua=next((c for c in capitoli if c.stato is not StatoComprensione.COMPRESO), None),
    )


def da_ripassare(lezioni: list[LezioneStudio]) -> list[VoceRipasso]:
    """I Capitoli da ripassare di tutte le Materie, dal più vecchio."""
    voci = [
        VoceRipasso(lezione.materia, lezione.data, capitolo)
        for lezione in sorted(lezioni, key=lambda lezione: (lezione.data, lezione.materia))
        for capitolo in lezione.capitoli
        if capitolo.stato is StatoComprensione.DA_RIPASSARE
    ]
    return voci


def barra_segmentata(contatori: dict[StatoComprensione, int]) -> list[SegmentoBarra]:
    """Larghezze proporzionali ai Capitoli esistenti: nessun totale del corso, nessuna percentuale
    di avanzamento. Gli stati a zero non compaiono."""
    totale = sum(contatori.values())
    if totale == 0:
        return []
    return [
        SegmentoBarra(stato, round(contatori[stato] * 100 / totale, 1))
        for stato in ORDINE_STATI
        if contatori.get(stato, 0) > 0
    ]


# Tinte ben distanziate: le prime Materie correnti non si confondono tra loro.
TINTE = (212, 340, 24, 176, 300, 52, 195, 10)


def colore_materia(materia: str, materie_correnti: list[str] | tuple[str, ...] = ()) -> int:
    """La tinta (0-359) della Materia. Le Materie correnti ne ricevono una in ordine di
    elenco; le altre una stabile dedotta dal nome."""
    if materia in materie_correnti:
        return TINTE[list(materie_correnti).index(materia) % len(TINTE)]
    return TINTE[zlib.crc32(materia.encode("utf-8")) % len(TINTE)]
