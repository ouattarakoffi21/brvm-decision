#!/bin/bash
# Aide à la décision BRVM : double-clique sur ce fichier pour lancer l'application.
cd "$(dirname "$0")" || exit 1

echo ""
echo "=============================================="
echo " Aide à la décision BRVM - lancement"
echo "=============================================="
echo ""

PY=""
for candidat in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidat" >/dev/null 2>&1 && \
       "$candidat" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"; then
        PY="$candidat"; break
    fi
done
if [ -z "$PY" ]; then
    echo "Python 3.11 ou plus récent est introuvable."
    echo "Télécharge-le sur https://www.python.org/downloads/ puis relance ce fichier."
    open "https://www.python.org/downloads/"
    read -r -p "Appuie sur Entrée pour fermer."
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "Première utilisation : installation en cours, patiente quelques minutes..."
    "$PY" -m venv .venv || { read -r -p "Échec. Entrée pour fermer."; exit 1; }
fi
if [ ! -f ".venv/installation_ok.txt" ]; then
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt || {
        echo "L'installation a échoué : vérifie ta connexion internet puis relance."
        read -r -p "Entrée pour fermer."; exit 1; }
    echo ok > .venv/installation_ok.txt
fi

echo ""
echo "L'application démarre : ton navigateur va s'ouvrir sur http://localhost:8501"
echo "Laisse cette fenêtre ouverte tant que tu utilises l'application."
echo ""
(sleep 8; open "http://localhost:8501") &
.venv/bin/python -m streamlit run app.py --server.port 8501
