-- Il testo trascritto sopravvive nel DB (a differenza degli Appunti, che
-- vengono archiviati come file: vedi CONTEXT.md -> Appunti). I volumi di
-- testo in gioco (una trascrizione di lezione) restano comodi in una colonna
-- TEXT, senza bisogno del meccanismo file+percorso usato per gli Appunti.

ALTER TABLE lezioni ADD COLUMN trascrizione TEXT;
