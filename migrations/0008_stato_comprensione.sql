-- Stato di comprensione di un Capitolo, scelto a mano dal fratello dal sito
-- (vedi CONTEXT.md e issue #14). Tutti i Capitoli partono da 'da_studiare'.

ALTER TABLE capitoli ADD COLUMN stato_comprensione TEXT NOT NULL DEFAULT 'da_studiare'
    CHECK (stato_comprensione IN ('da_studiare', 'in_corso', 'compreso', 'da_ripassare'));
