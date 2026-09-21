-- Capitoli di una Registrazione (vedi docs/adr/0003-lezione-materia-giorno-e-capitoli.md,
-- issue #10) e il nuovo stato 'segmentata' tra 'trascritta' ed 'elaborata'.
-- La posizione è quella dentro la Registrazione: l'ordine dentro la Lezione deriva
-- dall'arrivo delle Registrazioni, così rifare la segmentazione di una Registrazione
-- (dopo un'interruzione) sostituisce i suoi Capitoli senza duplicarli né riordinare gli altri.

ALTER TABLE registrazioni DROP CONSTRAINT registrazioni_stato_check;
ALTER TABLE registrazioni ADD CONSTRAINT registrazioni_stato_check CHECK (
    stato IN (
        'ricevuta', 'trascritta', 'segmentata', 'elaborata', 'archiviata', 'notificata', 'errore'
    )
);

CREATE TABLE capitoli (
    registrazione_id TEXT NOT NULL REFERENCES registrazioni (id) ON DELETE CASCADE,
    posizione INTEGER NOT NULL,
    titolo TEXT NOT NULL,
    testo TEXT NOT NULL,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (registrazione_id, posizione)
);
