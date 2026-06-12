@echo off
cd /d "%~dp0"
echo Verificando dependencias...
python -m pip install --quiet --upgrade imageio-ffmpeg
echo Abrindo o conversor...
python conversor_mp3.py
if errorlevel 1 pause
