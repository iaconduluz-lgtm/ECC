@echo off
REM Doble clic para abrir el tablero del monitor de cobre (Windows).
cd /d "%~dp0"
if not exist .venv (
  echo Instalando por primera vez, espera unos minutos...
  python -m venv .venv || (echo Necesitas instalar Python desde https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m streamlit run app.py
pause
