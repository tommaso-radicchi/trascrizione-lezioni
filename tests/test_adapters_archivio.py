from __future__ import annotations

from datetime import date
from pathlib import Path

from trascrizione_lezioni.adapters.archivio import ArchivioFile
from trascrizione_lezioni.dominio import Lezione, Registrazione


def crea_registrazione(id: str = "abcdef12-3456-7890-abcd-ef1234567890", **override: object) -> Registrazione:
    lezione = Lezione(
        id="lezione-1",
        materia=str(override.get("materia", "Analisi 1")),
        data=date(2026, 3, 5),
        chat_id="fratello-1",
    )
    return Registrazione(id=id, lezione=lezione, percorso_audio="/audio/lezione.ogg")


def test_salva_scrive_il_markdown_nella_cartella_della_materia(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)
    registrazione = crea_registrazione()

    percorso = archivio.salva(registrazione, "# Analisi 1\n\n## Riassunto\n...")

    contenuto = Path(percorso).read_text(encoding="utf-8")
    assert contenuto == "# Analisi 1\n\n## Riassunto\n..."
    assert Path(percorso).parent == tmp_path / "Analisi 1"
    assert "2026-03-05" in Path(percorso).name


def test_salva_crea_la_cartella_della_materia_se_non_esiste(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)
    registrazione = crea_registrazione(materia="Fisica 1")

    assert not (tmp_path / "Fisica 1").exists()

    archivio.salva(registrazione, "contenuto")

    assert (tmp_path / "Fisica 1").is_dir()


def test_salva_di_due_registrazioni_della_stessa_lezione_non_sovrascrive_i_file(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)
    registrazione_1 = crea_registrazione(id="11111111-0000-0000-0000-000000000000")
    registrazione_2 = crea_registrazione(id="22222222-0000-0000-0000-000000000000")

    percorso_1 = archivio.salva(registrazione_1, "contenuto 1")
    percorso_2 = archivio.salva(registrazione_2, "contenuto 2")

    assert percorso_1 != percorso_2
    assert Path(percorso_1).read_text(encoding="utf-8") == "contenuto 1"
    assert Path(percorso_2).read_text(encoding="utf-8") == "contenuto 2"
