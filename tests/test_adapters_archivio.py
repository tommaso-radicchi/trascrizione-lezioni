from __future__ import annotations

from datetime import date
from pathlib import Path

from trascrizione_lezioni.adapters.archivio import ArchivioFile
from trascrizione_lezioni.dominio import Lezione


def crea_lezione(**override: object) -> Lezione:
    valori: dict[str, object] = {
        "id": "abcdef12-3456-7890-abcd-ef1234567890",
        "materia": "Analisi 1",
        "data": date(2026, 3, 5),
        "percorso_audio": "/audio/lezione.ogg",
        "chat_id": "fratello-1",
    }
    valori.update(override)
    return Lezione(**valori)  # type: ignore[arg-type]


def test_salva_scrive_il_markdown_nella_cartella_della_materia(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)
    lezione = crea_lezione()

    percorso = archivio.salva(lezione, "# Analisi 1\n\n## Riassunto\n...")

    contenuto = Path(percorso).read_text(encoding="utf-8")
    assert contenuto == "# Analisi 1\n\n## Riassunto\n..."
    assert Path(percorso).parent == tmp_path / "Analisi 1"
    assert "2026-03-05" in Path(percorso).name


def test_salva_crea_la_cartella_della_materia_se_non_esiste(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)
    lezione = crea_lezione(materia="Fisica 1")

    assert not (tmp_path / "Fisica 1").exists()

    archivio.salva(lezione, "contenuto")

    assert (tmp_path / "Fisica 1").is_dir()


def test_salva_di_due_lezioni_diverse_non_sovrascrive_i_file(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)
    lezione_1 = crea_lezione(id="11111111-0000-0000-0000-000000000000")
    lezione_2 = crea_lezione(id="22222222-0000-0000-0000-000000000000")

    percorso_1 = archivio.salva(lezione_1, "contenuto 1")
    percorso_2 = archivio.salva(lezione_2, "contenuto 2")

    assert percorso_1 != percorso_2
    assert Path(percorso_1).read_text(encoding="utf-8") == "contenuto 1"
    assert Path(percorso_2).read_text(encoding="utf-8") == "contenuto 2"
