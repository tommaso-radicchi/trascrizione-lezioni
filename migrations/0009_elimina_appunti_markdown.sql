-- Il Markdown degli Appunti non si salva più nel DB: si ricompone dai Capitoli
-- (vedi docs/adr/0003, issue #11), e la colonna non è più usata dal codice (issue #13).
-- Applicare dopo aver fermato bot e Orchestratore (il codice precedente a #11 la leggeva).

ALTER TABLE registrazioni DROP COLUMN appunti_markdown;
