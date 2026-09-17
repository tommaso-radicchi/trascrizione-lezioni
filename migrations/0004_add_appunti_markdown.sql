-- Il Markdown degli Appunti sopravvive nel DB tra un passo e l'altro
-- dell'Orchestratore (stesso motivo della colonna trascrizione in
-- 0003): senza, andrebbe perso al primo ricaricamento prima che il
-- passo di archiviazione (issue #6) possa scriverlo su file.

ALTER TABLE lezioni ADD COLUMN appunti_markdown TEXT;
