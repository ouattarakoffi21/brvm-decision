"""Point d'entrée : streamlit run app.py"""
import streamlit as st

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
