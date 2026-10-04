import streamlit as st

from brvm import ui

cfg = ui.page("Tableau de bord", "Ce qu'il faut regarder aujourd'hui, en un coup d'œil.")
prep = ui.donnees(cfg)
ui.bandeau_donnees(prep)
res = ui.decisions(cfg)
tab = res["tableau"]

ui.tuiles([
    {"label": "Signaux d'achat", "valeur": int((tab["action"] == "ACHAT").sum()), "ton": "buy",
     "detail": "score et tendance au vert"},
    {"label": "Ventes ou allègements", "valeur": int(tab["action"].isin(["VENDRE", "ALLÉGER"]).sum()),
     "ton": "sell", "detail": "sur tes positions"},
    {"label": "À surveiller", "valeur": int((tab["action"] == "SURVEILLER").sum()), "ton": "watch",
     "detail": "bon score, tendance à confirmer"},
    {"label": "Titres écartés", "valeur": int((tab["action"] == "ÉCARTÉ").sum()), "ton": "out",
     "detail": "peu liquides ou données douteuses"},
])

for a in res["avertissements"]:
    st.warning(a)

gauche, droite = st.columns(2, gap="large")
with gauche:
    st.subheader("À traiter en priorité")
    urgent = tab[tab["action"].isin(["VENDRE", "ALLÉGER"])]
    if urgent.empty:
        st.info("Aucune vente à faire sur tes positions aujourd'hui.")
    for i, (t, r) in enumerate(urgent.iterrows()):
        ui.carte_signal(t, r, delai=i * 80)
with droite:
    st.subheader("Meilleures opportunités")
    achats = tab[tab["action"] == "ACHAT"].head(3)
    if achats.empty:
        st.info("Aucun signal d'achat aujourd'hui.")
    for i, (t, r) in enumerate(achats.iterrows()):
        ui.carte_signal(t, r, delai=i * 80)
    if len(achats):
        st.page_link("vues/signaux.py", label="Voir tous les signaux et les quantités proposées",
                     icon=":material/arrow_forward:")

st.subheader("Aller plus loin")
liens = [
    ("vues/rapport.py", "Rapport de recherche", ":material/query_stats:",
     "Top 10 selon ton profil, avec PER, croissance, dividende, risque et zones d'entrée."),
    ("vues/portefeuille.py", "Mon portefeuille", ":material/account_balance_wallet:",
     "Tes positions réelles, résultat net de frais et dividendes perçus."),
    ("vues/classement.py", "Classement", ":material/leaderboard:",
     "Tous les titres classés par score, avec la fiche détaillée de chacun."),
    ("vues/backtest.py", "Backtest", ":material/science:",
     "Ce qu'auraient donné les règles depuis 2016, face à la référence et au hasard."),
]
cols = st.columns(2)
for i, (page, titre, icone, texte) in enumerate(liens):
    with cols[i % 2]:
        st.page_link(page, label=titre, icon=icone)
        st.caption(texte)
