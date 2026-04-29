#!/usr/bin/env bash
# Arrancar ltxven
cd "/home/aisoe/aiproject/ltxven"
exec .venv/bin/streamlit run app.py     --server.port 8501     --server.address 0.0.0.0     --server.headless true
