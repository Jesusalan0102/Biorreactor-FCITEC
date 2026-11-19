@echo off
cd /d "%~dp0"
echo Creando tablas y tu usuario en TiDB...
python inicializar_bd.py
pause
