@echo off
cd /d "%~dp0api"
if not exist .venv py -m venv .venv
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if not exist .env (
  copy .env.example .env
  echo.
  echo Se creo api\.env. Complete los datos de SQL Server y vuelva a ejecutar este archivo.
  pause
  exit /b 0
)
python main.py
