# Trascrizione Lezioni

Sistema che trasforma le registrazioni audio delle lezioni di un fratello in appunti di studio, trascrivendo con Whisper e riassumendo con un LLM, il tutto in locale sull'infrastruttura Mac Mini / MSI Cyborg.

## Language

**Lezione**:
Una sessione di corso a cui il fratello ha assistito, esistente nel sistema come una Registrazione.
_Avoid_: corso, classe

**Registrazione**:
Il file audio grezzo di una Lezione, caricato dal fratello per essere processato.
_Avoid_: file, audio, upload

**Trascrizione**:
Il testo prodotto da Whisper a partire da una Registrazione.
_Avoid_: transcript, testo

**Appunti**:
L'output finale generato da un LLM a partire da una Trascrizione: un documento Markdown strutturato con titolo, data della Lezione, riassunto breve, punti chiave in elenco, ed eventuale sezione di argomenti/termini.
_Avoid_: note, riassunto (il riassunto è solo una sezione degli Appunti, non l'intero documento)

**Materia**:
La categoria/corso a cui appartiene una Lezione, usata per organizzare l'archivio degli Appunti. Scelta dal fratello tramite selettore, tra le sole Materie correnti (quelle che sta seguendo in quel momento), non dedotta automaticamente.
_Avoid_: corso (ambiguo con Lezione), soggetto
