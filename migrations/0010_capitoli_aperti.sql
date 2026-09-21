-- Quando il fratello ha aperto un Capitolo dal sito (issue #15): finché è NULL il Capitolo
-- è "nuovo". Un Capitolo rielaborato nasce con NULL, quindi torna nuovo.

ALTER TABLE capitoli ADD COLUMN aperto_il TIMESTAMPTZ;
