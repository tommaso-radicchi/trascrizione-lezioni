-- Schema per l'entità Lezione (vedi CONTEXT.md per il glossario di dominio).
-- L'indice su (materia, data) supporta le future query di aggregazione per i
-- resoconti settimanali senza richiedere una migrazione strutturale (ADR 0001).

CREATE TABLE lezioni (
    id TEXT PRIMARY KEY,
    materia TEXT NOT NULL,
    data DATE NOT NULL,
    stato TEXT NOT NULL CHECK (
        stato IN ('ricevuta', 'trascritta', 'elaborata', 'archiviata', 'notificata', 'errore')
    ),
    percorso_audio TEXT NOT NULL,
    percorso_trascrizione TEXT,
    percorso_appunti TEXT,
    tentativi INTEGER NOT NULL DEFAULT 0,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_lezioni_materia_data ON lezioni (materia, data);
