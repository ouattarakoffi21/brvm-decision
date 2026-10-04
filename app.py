"""Point d'entrée : streamlit run app.py"""
import importlib
import sys
import types
from pathlib import Path

import streamlit as st

# Après une mise à jour du code en ligne, Streamlit peut garder en mémoire l'ancienne
# version des modules brvm : on les recharge dès qu'un fichier a changé.
_ORDRE = ["config", "donnees", "qualite", "liquidite", "fondamental", "filtres", "signaux",
          "risque", "moteur", "backtest", "recherche", "direct", "ui"]
_etat = sys.modules.setdefault("_brvm_version", types.ModuleType("_brvm_version"))
_version = max(p.stat().st_mtime for p in (Path(__file__).parent / "brvm").glob("*.py"))
if getattr(_etat, "version", None) not in (None, _version):
    for nom in _ORDRE:
        if f"brvm.{nom}" in sys.modules:
            importlib.reload(sys.modules[f"brvm.{nom}"])
_etat.version = _version

st.set_page_config(page_title="BRVM Décision", page_icon="assets/icone.svg", layout="wide")
st.logo("assets/logo.svg", icon_image="assets/icone.svg", size="large")

navigation = st.navigation({
    "Décider": [
        st.Page("vues/accueil.py", title="Tableau de bord", icon=":material/space_dashboard:",
                default=True),
        st.Page("vues/signaux.py", title="Signaux du jour", icon=":material/traffic:"),
        st.Page("vues/direct.py", title="Séance en direct", icon=":material/sensors:"),
        st.Page("vues/rapport.py", title="Rapport de recherche", icon=":material/query_stats:"),
    ],
    "Suivre": [
        st.Page("vues/portefeuille.py", title="Mon portefeuille", icon=":material/account_balance_wallet:"),
        st.Page("vues/classement.py", title="Classement", icon=":material/leaderboard:"),
    ],
    "Comprendre": [
        st.Page("vues/backtest.py", title="Backtest", icon=":material/science:"),
        st.Page("vues/methodologie.py", title="Méthodologie", icon=":material/menu_book:"),
    ],
    "Réglages": [
        st.Page("vues/parametres.py", title="Paramètres", icon=":material/tune:"),
    ],
})
navigation.run()
