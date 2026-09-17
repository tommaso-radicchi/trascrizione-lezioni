@echo off
REM Avvia il server di trascrizione. Lanciato manualmente o dalla cartella
REM Startup di Windows (stesso pattern del collegamento Ollama.lnk).
set PYTHON=C:\Users\tomma\AppData\Local\Programs\Python\Python311\python.exe
set PATH=C:\Users\tomma\AppData\Local\Programs\Python\Python311\Lib\site-packages\nvidia\cublas\bin;C:\Users\tomma\AppData\Local\Programs\Python\Python311\Lib\site-packages\nvidia\cudnn\bin;%PATH%
cd /d "%~dp0"
%PYTHON% -m uvicorn server:app --host 0.0.0.0 --port 8001
