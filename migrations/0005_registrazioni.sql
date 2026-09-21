-- Una Lezione è ora Materia + giorno e raccoglie una o più Registrazioni
-- (vedi docs/adr/0003-lezione-materia-giorno-e-capitoli.md, issue #9).
-- Lo stato, l'audio, la trascrizione e gli appunti passano dalla Lezione alla
-- Registrazione. I dati esistenti vengono migrati: le righe di `lezioni` con
-- la stessa (materia, data) si fondono in una sola Lezione (la più vecchia) e
-- ciascuna diventa una Registrazione con lo stesso id di prima.

CREATE TABLE registrazioni (
    id TEXT PRIMARY KEY,
    lezione_id TEXT NOT NULL REFERENCES lezioni (id),
    stato TEXT NOT NULL CHECK (
        stato IN ('ricevuta', 'trascritta', 'elaborata', 'archiviata', 'notificata', 'errore')
    ),
    percorso_audio TEXT NOT NULL,
    trascrizione TEXT,
    appunti_markdown TEXT,
    percorso_appunti TEXT,
    tentativi INTEGER NOT NULL DEFAULT 0,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_registrazioni_lezione ON registrazioni (lezione_id, creato_il);

INSERT INTO registrazioni (
    id, lezione_id, stato, percorso_audio, trascrizione, appunti_markdown,
    percorso_appunti, tentativi, creato_il, aggiornato_il
)
SELECT l.id, principale.id, l.stato, l.percorso_audio, l.trascrizione, l.appunti_markdown,
       l.percorso_appunti, l.tentativi, l.creato_il, l.aggiornato_il
FROM lezioni l
JOIN (
    SELECT DISTINCT ON (materia, data) id, materia, data
    FROM lezioni
    ORDER BY materia, data, creato_il, id
) principale USING (materia, data);

DELETE FROM lezioni WHERE id NOT IN (SELECT lezione_id FROM registrazioni);

ALTER TABLE lezioni
    DROP COLUMN stato,
    DROP COLUMN percorso_audio,
    DROP COLUMN percorso_trascrizione,
    DROP COLUMN percorso_appunti,
    DROP COLUMN tentativi,
    DROP COLUMN trascrizione,
    DROP COLUMN appunti_markdown;

DROP INDEX idx_lezioni_materia_data;
CREATE UNIQUE INDEX idx_lezioni_materia_data ON lezioni (materia, data);
