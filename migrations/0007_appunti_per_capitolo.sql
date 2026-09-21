-- Appunti strutturati per Capitolo e quadro generale della Lezione
-- (vedi docs/adr/0003-lezione-materia-giorno-e-capitoli.md, issue #11).
-- Il Markdown in archivio è ricomposto da questi dati, non è più salvato nel DB:
-- registrazioni.appunti_markdown non è più usata (si elimina con la pulizia dell'archivio, #13).

ALTER TABLE capitoli ADD COLUMN appunti JSONB;
ALTER TABLE lezioni ADD COLUMN quadro_generale TEXT;
COMMENT ON COLUMN registrazioni.appunti_markdown IS 'Non più usata dal codice: da eliminare (issue #13)';
