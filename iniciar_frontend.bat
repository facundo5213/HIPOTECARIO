@echo off
cd /d "%~dp0frontend"
py -m http.server 5500 --bind 127.0.0.1
