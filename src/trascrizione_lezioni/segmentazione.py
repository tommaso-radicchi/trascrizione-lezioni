"""Segmentazione di una Trascrizione in Capitoli (vedi CONTEXT.md -> Capitolo).

Il LLM propone solo titolo e prime parole di ogni Capitolo; qui il testo originale
viene tagliato in modo deterministico, così una Trascrizione non è mai riscritta
dal modello e la concatenazione dei Capitoli è sempre identica all'originale."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .dominio import PropostaCapitolo, CapitoloTagliato
from .porte import ClientSegmentazione

PAROLE_MIN = 1200
PAROLE_MAX = 3000
TENTATIVI_SEGMENTAZIONE = 2
TITOLO_RIPIEGO = "Intera registrazione"

_FINE_FRASE = re.compile(r"[.!?…]['\")\]»]*$")


class SegmentazioneNonValida(Exception):
    """Il LLM ha risposto, ma non con Capitoli utilizzabili per questa Trascrizione."""


@dataclass(frozen=True)
class RisultatoSegmentazione:
    capitoli: list[CapitoloTagliato]
    # Valorizzato solo se si è ripiegato su un Capitolo generico: perché la segmentazione è fallita.
    motivo_ripiego: str | None


def segmenta(
    trascrizione: str,
    client: ClientSegmentazione,
    *,
    parole_min: int = PAROLE_MIN,
    parole_max: int = PAROLE_MAX,
) -> RisultatoSegmentazione:
    """Una risposta non valida viene ritentata una volta, poi si ripiega su un
    Capitolo generico. Gli errori di trasporto non vengono mascherati: si propagano
    ai tentativi dell'Orchestratore."""
    ultimo_errore: SegmentazioneNonValida | None = None
    for _ in range(TENTATIVI_SEGMENTAZIONE):
        try:
            proposte = client.proponi_capitoli(trascrizione)
            capitoli = taglia(
                trascrizione, proposte, parole_min=parole_min, parole_max=parole_max
            )
            return RisultatoSegmentazione(capitoli, motivo_ripiego=None)
        except SegmentazioneNonValida as errore:
            ultimo_errore = errore

    generico = [CapitoloTagliato(TITOLO_RIPIEGO, trascrizione)]
    return RisultatoSegmentazione(
        _spezza_lunghi(generico, parole_max), motivo_ripiego=str(ultimo_errore)
    )


def taglia(
    trascrizione: str,
    proposte: list[PropostaCapitolo],
    *,
    parole_min: int = PAROLE_MIN,
    parole_max: int = PAROLE_MAX,
) -> list[CapitoloTagliato]:
    if not proposte:
        raise SegmentazioneNonValida("Nessun Capitolo proposto")

    # Il primo Capitolo parte sempre dall'inizio: non si perde il testo prima della prima frase.
    inizi = [0]
    for indice, proposta in enumerate(proposte):
        if not proposta.titolo.strip():
            raise SegmentazioneNonValida(f"Il Capitolo {indice + 1} non ha un titolo")
        if not proposta.frase_inizio.strip():
            raise SegmentazioneNonValida(f"Il Capitolo «{proposta.titolo}» non ha una frase di inizio")
        if indice == 0:
            continue
        posizione = _trova_frase(trascrizione, proposta.frase_inizio, da=inizi[-1] + 1)
        if posizione is None:
            raise SegmentazioneNonValida(
                f"Frase di inizio non trovata per il Capitolo «{proposta.titolo}»: "
                f"{proposta.frase_inizio!r}"
            )
        inizi.append(posizione)

    fini = inizi[1:] + [len(trascrizione)]
    capitoli = [
        CapitoloTagliato(proposta.titolo.strip(), trascrizione[inizio:fine])
        for proposta, inizio, fine in zip(proposte, inizi, fini, strict=True)
    ]
    return _spezza_lunghi(_unisci_corti(capitoli, parole_min), parole_max)


def _trova_frase(testo: str, frase: str, *, da: int) -> int | None:
    # Confronto per parole: ignora maiuscole, punteggiatura e spazi diversi tra le parole.
    parole = re.findall(r"\w+", frase)
    if not parole:
        return None
    schema = r"\b" + r"\W+".join(re.escape(parola) for parola in parole)
    trovata = re.compile(schema, re.IGNORECASE).search(testo, da)
    return trovata.start() if trovata else None


def _numero_parole(testo: str) -> int:
    return len(testo.split())


def _unisci_corti(capitoli: list[CapitoloTagliato], parole_min: int) -> list[CapitoloTagliato]:
    lista = list(capitoli)
    while len(lista) > 1:
        corto = next(
            (i for i, capitolo in enumerate(lista) if _numero_parole(capitolo.testo) < parole_min),
            None,
        )
        if corto is None:
            break
        # Un Capitolo corto si unisce al precedente; se è il primo, al successivo.
        prima, dopo = (corto - 1, corto) if corto > 0 else (corto, corto + 1)
        piu_lungo = (
            lista[prima]
            if _numero_parole(lista[prima].testo) >= _numero_parole(lista[dopo].testo)
            else lista[dopo]
        )
        unito = CapitoloTagliato(piu_lungo.titolo, lista[prima].testo + lista[dopo].testo)
        lista[prima : dopo + 1] = [unito]
    return lista


def _spezza_lunghi(capitoli: list[CapitoloTagliato], parole_max: int) -> list[CapitoloTagliato]:
    risultato: list[CapitoloTagliato] = []
    for capitolo in capitoli:
        parti = math.ceil(_numero_parole(capitolo.testo) / parole_max)
        if parti <= 1:
            risultato.append(capitolo)
            continue
        pezzi = _dividi_a_fine_frase(capitolo.testo, parti)
        risultato += [
            CapitoloTagliato(f"{capitolo.titolo} ({numero}/{len(pezzi)})", pezzo)
            for numero, pezzo in enumerate(pezzi, start=1)
        ]
    return risultato


def _dividi_a_fine_frase(testo: str, parti: int) -> list[str]:
    inizi_parola = [trovata.start() for trovata in re.finditer(r"\S+", testo)]
    parole = testo.split()
    dimensione = len(parole) / parti
    finestra = max(10, int(dimensione * 0.2))

    tagli: list[int] = []
    for k in range(1, parti):
        obiettivo = round(k * dimensione)
        minimo = tagli[-1] + 1 if tagli else 1
        candidati = range(max(obiettivo, minimo), min(obiettivo + finestra, len(parole) - 1) + 1)
        # Si taglia dopo una parola che chiude una frase; altrimenti esattamente all'obiettivo.
        taglio = next(
            (j for j in candidati if _FINE_FRASE.search(parole[j - 1])),
            max(obiettivo, minimo),
        )
        if taglio >= len(parole):
            break
        tagli.append(taglio)

    estremi = [0] + [inizi_parola[taglio] for taglio in tagli] + [len(testo)]
    return [testo[a:b] for a, b in zip(estremi, estremi[1:], strict=False)]
