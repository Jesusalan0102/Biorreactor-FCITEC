@echo off
cd /d "%~dp0"
echo Instalando dependencias...
python -m pip install -r requirements.txt
pause
