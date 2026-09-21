# Trascrizione Lezioni

Vedi `CONTEXT.md` per il glossario di dominio e `docs/adr/` per le decisioni architetturali.

## Ollama (generazione degli Appunti)

Gli Appunti si generano con Ollama **sul Mac Mini** e un modello cloud (`OLLAMA_MODEL`, es.
`gemma4:31b-cloud`), quindi non dipendono dall'MSI: l'MSI resta acceso on-demand solo per
Whisper (vedi `docs/adr/0002-elaborazione-on-demand-gpu.md`).

Setup, una volta sola:

```bash
systemctl enable --now ollama   # servizio sempre attivo
ollama signin                   # i modelli cloud richiedono l'accesso
```

In `.env` imposta `OLLAMA_BASE_URL=http://localhost:11434` (vedi `.env.example`). Per
verificare: `ollama run gemma4:31b-cloud "ok"` deve rispondere senza `Unauthorized`.

## Sito di studio

App web (FastAPI) sul Mac Mini: dashboard per Materia, hub delle Lezioni e lettura per Capitolo,
con lo Stato di comprensione scelto a mano. Non ha login: ascolta solo su `127.0.0.1` e si
raggiunge dall'iPhone via Tailscale.

```bash
# una volta sola, dopo aver applicato le migrazioni al database
cp systemd/trascrizione-lezioni-web.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now trascrizione-lezioni-web

# lo espone sulla tailnet con HTTPS (solo ai dispositivi del tuo account Tailscale)
tailscale serve --bg 8000
tailscale serve status        # mostra l'indirizzo https://<macchina>.<tailnet>.ts.net
```

Sull'iPhone: installa l'app Tailscale, accedi con lo stesso account (o accetta l'invito a
condividere il Mac Mini), apri l'indirizzo in Safari e usa "Aggiungi alla schermata Home".

## Test

```bash
uv run pytest
```

I test del `RepositoryPostgres` (`tests/test_adapters_postgres.py`) girano contro un Postgres
reale e **svuotano le tabelle `lezioni` e `registrazioni`**. Per questo usano `DATABASE_URL_TEST`, mai
`DATABASE_URL`: se la variabile manca vengono saltati, e si rifiutano di partire se punta al
database di produzione o a uno il cui nome non finisce in `_test`.

### Creare il database di test

Serve una volta sola, o dopo aver ricreato il container Postgres (lo script di init del
container applica le migrazioni solo al database principale).

```bash
docker compose up -d postgres

docker compose exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE trascrizione_lezioni_test;"'

for f in migrations/*.sql; do
  docker compose exec -T postgres sh -c \
    'psql -q -U "$POSTGRES_USER" -d trascrizione_lezioni_test' < "$f"
done
```

Poi imposta in `.env`, con le stesse credenziali di `DATABASE_URL` e il database `_test`
(vedi `.env.example`):

```
DATABASE_URL_TEST=postgresql://<utente>:<password>@localhost:5432/trascrizione_lezioni_test
```

Dopo ogni nuova migrazione in `migrations/`, applicala anche al database di test:

```bash
docker compose exec -T postgres sh -c \
  'psql -q -U "$POSTGRES_USER" -d trascrizione_lezioni_test' < migrations/<nuova>.sql
```
