from __future__ import annotations

from trascrizione_lezioni.adapters.fake import ClientTelegramFake, RepositoryFake
from datetime import date

from trascrizione_lezioni.dominio import Stato
from trascrizione_lezioni.ingest import GestoreIngest

MATERIE = ["Analisi 1", "Fisica 1"]
ADMIN_CHAT_ID = "admin-42"
FRATELLO_CHAT_ID = "fratello-1"


def crea_gestore(
    *,
    client_telegram: ClientTelegramFake | None = None,
    repository: RepositoryFake | None = None,
    fratello_chat_id: str | None = FRATELLO_CHAT_ID,
) -> tuple[GestoreIngest, ClientTelegramFake, RepositoryFake]:
    client_telegram = client_telegram or ClientTelegramFake()
    repository = repository or RepositoryFake()
    gestore = GestoreIngest(
        repository=repository,
        client_telegram=client_telegram,
        materie_correnti=MATERIE,
        admin_chat_id=ADMIN_CHAT_ID,
        fratello_chat_id=fratello_chat_id,
    )
    return gestore, client_telegram, repository


def test_audio_ricevuto_fa_apparire_il_selettore_delle_materie_correnti() -> None:
    gestore, client_telegram, _ = crea_gestore()

    gestore.audio_ricevuto(chat_id="fratello-1", percorso_audio="/audio/lezione1.ogg")

    assert client_telegram.materie_richieste == [("fratello-1", MATERIE)]


def test_selezione_materia_crea_una_lezione_e_una_registrazione_ricevuta_e_conferma() -> None:
    gestore, client_telegram, repository = crea_gestore()
    gestore.audio_ricevuto(chat_id="fratello-1", percorso_audio="/audio/lezione1.ogg")

    registrazione = gestore.materia_selezionata(chat_id="fratello-1", materia="Fisica 1")

    assert registrazione is not None
    assert registrazione.lezione.materia == "Fisica 1"
    assert registrazione.lezione.data == date.today()
    assert registrazione.percorso_audio == "/audio/lezione1.ogg"
    assert registrazione.lezione.chat_id == "fratello-1"
    assert registrazione.stato is Stato.RICEVUTA
    assert repository.registrazioni() == [registrazione]
    assert repository.lezioni() == [registrazione.lezione]
    assert client_telegram.conferme_inviate == ["fratello-1"]


def test_due_audio_della_stessa_materia_nello_stesso_giorno_finiscono_nella_stessa_lezione() -> None:
    gestore, client_telegram, repository = crea_gestore()

    gestore.audio_ricevuto(chat_id="fratello-1", percorso_audio="/audio/prima.ogg")
    prima = gestore.materia_selezionata(chat_id="fratello-1", materia="Fisica 1")
    gestore.audio_ricevuto(chat_id="fratello-1", percorso_audio="/audio/seconda.ogg")
    seconda = gestore.materia_selezionata(chat_id="fratello-1", materia="Fisica 1")

    assert prima is not None and seconda is not None
    assert prima.id != seconda.id
    assert prima.lezione.id == seconda.lezione.id
    assert len(repository.lezioni()) == 1
    assert [r.percorso_audio for r in repository.registrazioni()] == [
        "/audio/prima.ogg",
        "/audio/seconda.ogg",
    ]
    assert client_telegram.conferme_inviate == ["fratello-1", "fratello-1"]


def test_materie_diverse_nello_stesso_giorno_sono_lezioni_diverse() -> None:
    gestore, _, repository = crea_gestore()

    gestore.audio_ricevuto(chat_id="fratello-1", percorso_audio="/audio/a.ogg")
    gestore.materia_selezionata(chat_id="fratello-1", materia="Fisica 1")
    gestore.audio_ricevuto(chat_id="fratello-1", percorso_audio="/audio/b.ogg")
    gestore.materia_selezionata(chat_id="fratello-1", materia="Analisi 1")

    assert len(repository.lezioni()) == 2


def test_materia_non_corrente_viene_rifiutata_senza_creare_lezioni() -> None:
    gestore, client_telegram, repository = crea_gestore()
    gestore.audio_ricevuto(chat_id="fratello-1", percorso_audio="/audio/lezione1.ogg")

    registrazione = gestore.materia_selezionata(
        chat_id="fratello-1", materia="Materia inesistente"
    )

    assert registrazione is None
    assert repository.registrazioni() == []
    assert client_telegram.conferme_inviate == []


def test_la_chat_admin_viene_distinta_da_quella_del_fratello() -> None:
    gestore, _, _ = crea_gestore()

    assert gestore.e_chat_admin(ADMIN_CHAT_ID) is True
    assert gestore.e_chat_admin(FRATELLO_CHAT_ID) is False


def test_una_chat_sconosciuta_viene_ignorata_quando_il_fratello_e_configurato() -> None:
    gestore, client_telegram, repository = crea_gestore(fratello_chat_id=FRATELLO_CHAT_ID)

    gestore.audio_ricevuto(chat_id="estraneo-99", percorso_audio="/audio/lezione1.ogg")

    assert client_telegram.materie_richieste == []
    assert repository.registrazioni() == []


def test_admin_puo_comunque_avviare_un_upload() -> None:
    gestore, client_telegram, _ = crea_gestore(fratello_chat_id=FRATELLO_CHAT_ID)

    gestore.audio_ricevuto(chat_id=ADMIN_CHAT_ID, percorso_audio="/audio/lezione1.ogg")

    assert client_telegram.materie_richieste == [(ADMIN_CHAT_ID, MATERIE)]


def test_senza_fratello_configurato_qualunque_chat_puo_avviare_un_upload() -> None:
    gestore, client_telegram, _ = crea_gestore(fratello_chat_id=None)

    gestore.audio_ricevuto(chat_id="chat-mai-vista-prima", percorso_audio="/audio/lezione1.ogg")

    assert client_telegram.materie_richieste == [("chat-mai-vista-prima", MATERIE)]
