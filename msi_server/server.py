"""Server HTTP nativo per la trascrizione con faster-whisper sulla GPU
dell'MSI, stesso pattern di Ollama nativo (niente Docker, accesso diretto
alla GPU). Avviato da avvia_server.bat. Vedi ADR 0002 e issue #4.

Il modello viene caricato e scaricato ad ogni richiesta, non tenuto
residente in VRAM: un modello caricato a riposo genera un utilizzo GPU
osservato tra il 20% e il 30% (verificato spegnendo il server: senza
modello caricato l'utilizzo scende a 0%), che romperebbe il controllo
di disponibilità GPU lato Mac Mini — pensato per non interferire mai
con l'uso personale della macchina (ADR 0002). Il costo è qualche
secondo di ricarica per ogni Lezione, accettabile: non c'è urgenza.
"""

from __future__ import annotations

import gc
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from faster_whisper import WhisperModel

MODELLO = os.environ.get("WHISPER_MODEL", "medium")
LINGUA = os.environ.get("WHISPER_LANGUAGE", "it")

app = FastAPI()


@app.post("/trascrivi")
def trascrivi(file: UploadFile) -> dict[str, str]:
    suffisso = Path(file.filename or "audio").suffix or ".audio"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffisso) as tmp:
        shutil.copyfileobj(file.file, tmp)
        percorso_temp = tmp.name

    try:
        modello = WhisperModel(MODELLO, device="cuda", compute_type="float16")
        try:
            segmenti, _ = modello.transcribe(percorso_temp, language=LINGUA)
            testo = " ".join(segmento.text.strip() for segmento in segmenti)
        finally:
            del modello
            gc.collect()
    finally:
        os.remove(percorso_temp)

    return {"testo": testo}


@app.get("/stato-gpu")
def stato_gpu() -> dict[str, float]:
    try:
        risultato = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        utilizzo, vram_libera = risultato.stdout.strip().split(",")
        return {
            "utilizzo_percento": float(utilizzo.strip()),
            "vram_libera_mb": float(vram_libera.strip()),
        }
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as errore:
        raise HTTPException(status_code=503, detail=f"GPU non pronta: {errore}") from errore
