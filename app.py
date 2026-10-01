"""Point d'entrée : streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="Aide à la décision BRVM", page_icon="📈", layout="wide")

navigation = st.navigation([
    st.Page("vues/accueil.py", title="Accueil", icon="🏠", default=True),
    st.Page("vues/signaux.py", title="Signaux du jour", icon="🚦"),
    st.Page("vues/classement.py", title="Classement", icon="🏆"),
    st.Page("vues/portefeuille.py", title="Mon portefeuille", icon="💼"),
    st.Page("vues/backtest.py", title="Backtest", icon="🧪"),
    st.Page("vues/parametres.py", title="Paramètres", icon="⚙️"),
    st.Page("vues/methodologie.py", title="Méthodologie", icon="📘"),
])
navigation.run()
