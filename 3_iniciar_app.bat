@echo off
rem Reinicia la app sola si se cierra por error (pruebas de 24 h).
rem Para salir de verdad: cierra esta ventana negra.
cd /d "%~dp0"
:inicio
python controlfisicoV2.py
echo [%date% %time%] La app se cerro. Reiniciando en 10 s... (cierra esta ventana para detener)
timeout /t 10 /nobreak >nul
goto inicio
