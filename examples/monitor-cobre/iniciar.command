#!/bin/bash
# Doble clic para abrir el tablero del monitor de cobre (Mac). En Linux: bash iniciar.command
cd "$(dirname "$0")" || exit 1
if [ ! -d .venv ]; then
  echo "Instalando por primera vez, espera unos minutos..."
  python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt || exit 1
fi
.venv/bin/python -m streamlit run app.py
