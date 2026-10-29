@echo off
setlocal
cd /d "%~dp0"
set "CTF_ENGINE=%ProgramFiles%\7-Zip\7z.exe"
if not exist "%CTF_ENGINE%" (
    echo Installez 7-Zip depuis https://www.7-zip.org/ ou adaptez CTF_ENGINE.
    pause
    exit /b 1
)
if exist "demo.zip" goto :exists
if exist "demo.7z" goto :exists
"%CTF_ENGINE%" a -tzip -mem=AES256 -pCTF42 -y demo.zip preuve.txt
if errorlevel 1 goto :error
"%CTF_ENGINE%" a -t7z -mhe=on -pCTF42 -y demo.7z preuve.txt
if errorlevel 1 goto :error
echo Archives creees. Mot de passe connu : CTF42. Liste : mots-demo.txt.
pause
exit /b 0
:exists
echo Une archive demo existe deja. Deplacez-la avant de recreer les exemples.
pause
exit /b 1
:error
echo La creation a echoue. Consultez la sortie 7-Zip ci-dessus.
pause
exit /b 1
