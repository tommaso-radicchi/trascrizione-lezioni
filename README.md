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

Per avere il link al primo Capitolo nelle notifiche Telegram, metti in `.env` l'indirizzo che mostra
`tailscale serve status` come `WEB_BASE_URL` (senza, le notifiche escono senza link).

Sull'iPhone: installa l'app Tailscale, accedi con lo stesso account (o accetta l'invito a
condividere il Mac Mini), apri l'indirizzo in Safari e usa "Aggiungi alla schermata Home".

## Sorveglianza

Ogni 5 minuti un timer systemd controlla che bot, Orchestratore e sito siano attivi, che il
database risponda e che nessuna Registrazione sia ferma da più di 12 ore. Quando compare un
problema, e quando tutto torna a posto, scrive all'admin su Telegram (una volta, non a ogni giro).

Se il Mac Mini è spento o senza internet non può avvisare nessuno: per questo a ogni giro manda
anche un battito a [Healthchecks.io](https://healthchecks.io). Se i battiti smettono di arrivare,
è Healthchecks ad avvisarti da fuori.

Setup, una volta sola:

1. Su healthchecks.io (piano gratuito) crea un check con **Period 5 minuti** e **Grace 10 minuti**.
2. In *Integrations* aggiungi **Telegram** e segui le istruzioni del loro bot.
3. Copia il *Ping URL* del check in `.env` come `HEALTHCHECKS_PING_URL`.
4. Installa il timer:

```bash
cp systemd/trascrizione-lezioni-sorveglianza.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now trascrizione-lezioni-sorveglianza.timer
```

Per un giro a mano: `uv run python -m trascrizione_lezioni.sorveglianza`. Lo stato degli ultimi
problemi notificati è in `~/.local/state/trascrizione-lezioni/sorveglianza.json`.

## Rielaborare una Lezione

Dopo un cambio di formato o di prompt, o per una Lezione elaborata dal flusso vecchio:

```bash
uv run python -m trascrizione_lezioni.rielabora "Matematica Generale" 2026-09-21
```

Riporta le Registrazioni della Lezione a "trascritta" (le Trascrizioni si conservano) e
l'Orchestratore in esecuzione rifà segmentazione, Appunti, archiviazione e notifica. Si
rifiuta se la Lezione è ancora in lavorazione, o se il fratello ha già scelto lo stato di
comprensione dei Capitoli (si perderebbe): `--forza` per procedere comunque. Il file della
Lezione in `archivio/` si riscrive; i file vecchi con l'id nel nome vanno tolti a mano.

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
