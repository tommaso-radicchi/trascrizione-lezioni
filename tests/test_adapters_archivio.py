from __future__ import annotations

from datetime import date
from pathlib import Path

from trascrizione_lezioni.adapters.archivio import ArchivioFile
from trascrizione_lezioni.dominio import Lezione


def crea_lezione(materia: str = "Analisi 1", data: date = date(2026, 3, 5)) -> Lezione:
    return Lezione(id="lezione-1", materia=materia, data=data, chat_id="fratello-1")


def test_salva_scrive_il_markdown_nella_cartella_della_materia(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)

    percorso = archivio.salva(crea_lezione(), "# Analisi 1\n\n## Riassunto\n...")

    assert Path(percorso).read_text(encoding="utf-8") == "# Analisi 1\n\n## Riassunto\n..."
    assert Path(percorso).parent == tmp_path / "Analisi 1"
    assert Path(percorso).name == "2026-03-05.md"


def test_salva_crea_la_cartella_della_materia_se_non_esiste(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)

    assert not (tmp_path / "Fisica 1").exists()

    archivio.salva(crea_lezione(materia="Fisica 1"), "contenuto")

    assert (tmp_path / "Fisica 1").is_dir()


def test_risalvare_la_stessa_lezione_sovrascrive_il_suo_file(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)

    percorso_1 = archivio.salva(crea_lezione(), "prima versione")
    percorso_2 = archivio.salva(crea_lezione(), "versione con il secondo audio")

    assert percorso_1 == percorso_2
    assert Path(percorso_2).read_text(encoding="utf-8") == "versione con il secondo audio"
    assert len(list((tmp_path / "Analisi 1").iterdir())) == 1


def test_lezioni_di_materie_o_giorni_diversi_non_si_sovrascrivono(tmp_path: Path) -> None:
    archivio = ArchivioFile(cartella_radice=tmp_path)

    percorsi = {
        archivio.salva(crea_lezione(materia="Analisi 1"), "a"),
        archivio.salva(crea_lezione(materia="Fisica 1"), "b"),
        archivio.salva(crea_lezione(data=date(2026, 3, 6)), "c"),
    }

    assert len(percorsi) == 3
