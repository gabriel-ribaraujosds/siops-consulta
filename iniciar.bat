@echo off
echo Iniciando SIOPS - Consulta de Despesas por Subfuncao...
cd /d "%~dp0"
streamlit run app.py --server.port 8501
pause
