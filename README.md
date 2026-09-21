# Trascrizione Lezioni

Vedi `CONTEXT.md` per il glossario di dominio e `docs/adr/` per le decisioni architetturali.

## Test

```bash
uv run pytest
```

I test del `RepositoryPostgres` (`tests/test_adapters_postgres.py`) girano contro un Postgres
reale e **svuotano la tabella `lezioni`**. Per questo usano `DATABASE_URL_TEST`, mai
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
