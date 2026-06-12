@echo off
cd /d "%~dp0"
echo Instalando/atualizando dependencias (so na primeira vez demora)...
python -m pip install --quiet --upgrade yt-dlp imageio-ffmpeg
echo Abrindo o programa...
python baixar_mp3.py
if errorlevel 1 pause
