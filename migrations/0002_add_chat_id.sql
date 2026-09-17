-- Il chat_id Telegram di provenienza della Lezione, per sapere a chi
-- rispondere con gli Appunti finiti (vedi issue #3).
-- DEFAULT '' evita che l'ALTER fallisca su righe esistenti; rimosso subito
-- dopo perché il dominio richiede sempre un chat_id per le righe nuove.

ALTER TABLE lezioni ADD COLUMN chat_id TEXT NOT NULL DEFAULT '';
ALTER TABLE lezioni ALTER COLUMN chat_id DROP DEFAULT;
