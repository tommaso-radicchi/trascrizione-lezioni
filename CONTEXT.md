# Trascrizione Lezioni

Sistema che trasforma le registrazioni audio delle lezioni di un fratello in appunti di studio, trascrivendo con Whisper e riassumendo con un LLM, e li rende consultabili in un sito web privato (dashboard per Materia, lettura per Capitolo). Whisper gira sull'MSI Cyborg, tutto il resto sul Mac Mini.

## Language

**Lezione**:
Una sessione di corso a cui il fratello ha assistito, identificata da Materia + giorno. Può essere composta da più Registrazioni (tipicamente due, per la pausa a metà) e raccoglie i Capitoli di tutte.
_Avoid_: corso, classe

**Registrazione**:
Un file audio grezzo di una Lezione, caricato dal fratello per essere processato. Una Lezione ne ha una o più; ciascuna viene elaborata appena arriva, senza aspettare le altre.
_Avoid_: file, audio, upload

**Trascrizione**:
Il testo prodotto da Whisper a partire da una Registrazione.
_Avoid_: transcript, testo

**Capitolo**:
Un pezzo tematico di una Lezione (un argomento), ottenuto segmentando la Trascrizione di una Registrazione. Ha titolo, riassunto breve, punti chiave, termini con definizioni, eventuali passaggi "Da ripassare", domande di autovalutazione con risposta nascosta, e il ritaglio esatto della Trascrizione da cui deriva. I Capitoli di una Lezione sono accodati nell'ordine di arrivo delle Registrazioni; ciascuno genera i suoi Appunti una sola volta. Ha uno Stato di comprensione.
_Avoid_: blocco, sezione, argomento (l'argomento è il tema, il Capitolo è l'unità dati)

**Appunti**:
I contenuti generati da un LLM per un Capitolo. Gli Appunti di una Lezione sono la composizione dei suoi Capitoli, con in cima un quadro generale e l'elenco degli argomenti (ricalcolato dai riassunti dei Capitoli a ogni nuovo Capitolo). Il Markdown in archivio è un prodotto derivato, sempre ricomposto dai dati strutturati.
_Avoid_: note, riassunto (il riassunto è solo una sezione degli Appunti, non l'intero documento)

**Stato di comprensione**:
Lo stato di un Capitolo scelto a mano dal fratello: da studiare, in corso, compreso, da ripassare. Non è calcolato né dedotto dal sistema.
_Avoid_: progresso, completamento

**Materia**:
La categoria/corso a cui appartiene una Lezione, usata per organizzare l'archivio degli Appunti e la dashboard. Scelta dal fratello tramite selettore, tra le sole Materie correnti (quelle che sta seguendo in quel momento), non dedotta automaticamente.
_Avoid_: corso (ambiguo con Lezione), soggetto
