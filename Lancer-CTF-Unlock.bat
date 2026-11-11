@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.14 -m venv .venv
    if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:2] == (3,14), 'Python 3.14 requis'"
if errorlevel 1 goto :oldenv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :error
exit /b 0
:oldenv
echo.
echo Le dossier .venv utilise une autre version de Python.
echo Renommez-le en .venv-ancien, puis relancez ce fichier avec Python 3.14 installe.
echo Aucun environnement existant n'a ete supprime.
pause
exit /b 1
:error
echo.
echo CTF Unlock n'a pas pu demarrer. Consultez l'erreur ci-dessus.
echo Installez Python 3.14 64 bits avec le lanceur py depuis python.org.
pause
exit /b 1
