"""Composizione del Markdown di una Lezione dai suoi Capitoli (vedi CONTEXT.md -> Appunti).

Funzione pura e deterministica: il Markdown in archivio è un prodotto derivato,
quindi cambiare il formato significa cambiare questo file e ricomporre dai dati,
senza richiamare il LLM."""

from __future__ import annotations

from .dominio import AppuntiCapitolo, Capitolo, Lezione


def componi_markdown(lezione: Lezione, capitoli: list[Capitolo]) -> str:
    """Compone i Capitoli già elaborati, nell'ordine ricevuto; gli altri non compaiono."""
    elaborati = [
        (capitolo.titolo, capitolo.appunti) for capitolo in capitoli if capitolo.appunti is not None
    ]

    parti = [
        f"# {lezione.materia}",
        f"**Data**: {lezione.data.strftime('%d/%m/%Y')}",
    ]
    if lezione.quadro_generale:
        parti.append(f"## Quadro generale\n\n{lezione.quadro_generale.strip()}")
    parti.append(
        "**Argomenti**\n\n"
        + "\n".join(f"{numero}. {titolo}" for numero, (titolo, _) in enumerate(elaborati, 1))
    )
    for numero, (titolo, appunti) in enumerate(elaborati, 1):
        parti.append(_componi_capitolo(numero, titolo, appunti))

    return "\n\n".join(parti) + "\n"


def _componi_capitolo(numero: int, titolo: str, appunti: AppuntiCapitolo) -> str:
    sezioni = [f"## {numero}. {titolo}", f"### Riassunto\n\n{appunti.riassunto.strip()}"]

    if appunti.punti_chiave:
        sezioni.append("### Punti chiave\n\n" + "\n".join(f"- {p}" for p in appunti.punti_chiave))
    if appunti.termini:
        sezioni.append(
            "### Termini\n\n"
            + "\n".join(f"- **{t.termine}**: {t.definizione}" for t in appunti.termini)
        )
    if appunti.da_ripassare:
        sezioni.append("### Da ripassare\n\n" + "\n".join(f"- {p}" for p in appunti.da_ripassare))
    if appunti.domande:
        domande = [
            f"**{n}. {d.domanda}**\n\n"
            f"<details>\n<summary>Risposta</summary>\n\n{d.risposta.strip()}\n\n</details>"
            for n, d in enumerate(appunti.domande, 1)
        ]
        sezioni.append("### Domande\n\n" + "\n\n".join(domande))

    return "\n\n".join(sezioni)
