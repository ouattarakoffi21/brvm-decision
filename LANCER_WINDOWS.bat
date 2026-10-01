@echo off
chcp 65001 >nul
title Aide a la decision BRVM
cd /d "%~dp0"

echo.
echo  ==============================================
echo   Aide a la decision BRVM - lancement
echo  ==============================================
echo.

REM ---- 1. Trouver Python (3.11 ou plus recent)
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY goto :pas_de_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto :pas_de_python

REM ---- 2. Premiere fois : environnement et bibliotheques (quelques minutes)
if not exist ".venv\Scripts\python.exe" (
    echo  Premiere utilisation : installation en cours, patiente quelques minutes...
    %PY% -m venv .venv
    if errorlevel 1 goto :erreur_installation
)
if not exist ".venv\installation_ok.txt" (
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :erreur_installation
    echo ok> ".venv\installation_ok.txt"
)

REM ---- 3. Ouvrir le navigateur dans quelques secondes, puis lancer l'application
echo.
echo  L'application demarre. Ton navigateur va s'ouvrir sur http://localhost:8501
echo  Si ce n'est pas le cas, ouvre cette adresse toi-meme.
echo  IMPORTANT : laisse cette fenetre ouverte tant que tu utilises l'application.
echo.
start "" cmd /c "timeout /t 8 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
echo.
echo  L'application s'est arretee.
pause
exit /b 0

:pas_de_python
echo  Python 3.11 ou plus recent est introuvable sur cet ordinateur.
echo.
echo  1. Telecharge Python sur https://www.python.org/downloads/
echo  2. A l'installation, COCHE la case "Add python.exe to PATH" (en bas de la premiere fenetre).
echo  3. Ferme cette fenetre puis double-clique a nouveau sur LANCER_WINDOWS.bat
echo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:erreur_installation
echo.
echo  L'installation des bibliotheques a echoue (voir le message ci-dessus).
echo  Verifie ta connexion internet, puis relance. Si l'erreur persiste,
echo  fais une capture de cette fenetre et envoie-la.
if exist ".venv\installation_ok.txt" del ".venv\installation_ok.txt"
pause
exit /b 1
