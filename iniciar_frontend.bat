@echo off
cd /d "%~dp0frontend"
py -m http.server 5010 --bind 0.0.0.0
