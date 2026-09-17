# Postgres invece di SQLite per il tracking

Il tracking di Lezioni/Appunti (stato, retry, percorsi file) ha un volume bassissimo e gira su una singola macchina, il che farebbe propendere per SQLite. Scegliamo comunque Postgres in Docker Compose sul Mac Mini (accanto a OpenWebUI, già nello stesso pattern operativo) perché il prossimo passo pianificato — resoconti settimanali e una dashboard, attesi entro pochi giorni — beneficerà di aggregazioni relazionali e potenzialmente di ricerca semantica sugli Appunti via `pgvector`; partire con SQLite significherebbe riscrivere lo schema quasi subito.
