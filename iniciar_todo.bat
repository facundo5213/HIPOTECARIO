@echo off
REM Levanta la API y el frontend juntos, cada uno en su propia ventana.
REM Requiere que esta carpeta este en una unidad MAPEADA (ej. Z:\), no en
REM una ruta UNC (\\servidor\carpeta) sin mapear -- cmd.exe no puede fijar
REM su directorio actual en una ruta UNC.
start "API - Reglamentaciones Crediticias" cmd /k "%~dp0iniciar_api.bat"
timeout /t 3 /nobreak >nul
start "Frontend - Reglamentaciones Crediticias" cmd /k "%~dp0iniciar_frontend.bat"
