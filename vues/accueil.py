"""Point d'entrée : streamlit run app.py"""
import streamlit as st

from brvm import ui

cfg = ui.page("Aide à la décision BRVM")
prep = ui.donnees(cfg)
ui.bandeau_donnees(prep)
res = ui.decisions(cfg)
tab = res["tableau"]

col = st.columns(4)
col[0].metric("Signaux d'achat", int((tab["action"] == "ACHAT").sum()))
col[1].metric("Ventes / allègements", int(tab["action"].isin(["VENDRE", "ALLÉGER"]).sum()))
col[2].metric("À surveiller", int((tab["action"] == "SURVEILLER").sum()))
col[3].metric("Titres écartés", int((tab["action"] == "ÉCARTÉ").sum()))

for a in res["avertissements"]:
    st.warning(a)

urgent = tab[tab["action"].isin(["VENDRE", "ALLÉGER"])]
if len(urgent):
    st.subheader("À traiter en priorité (positions détenues)")
    for t, r in urgent.iterrows():
        st.markdown(f"{ui.COULEURS_ACTION[r['action']]} **{r['action']} {t}** "
                    f"({r['societe']}) : {r['justification']}")

st.subheader("Navigation")
st.markdown("""
- **Signaux du jour** : quoi acheter, vendre ou surveiller, avec la justification et les quantités proposées.
- **Classement** : tous les titres classés par score, et la fiche détaillée de chacun.
- **Mon portefeuille** : tes positions réelles, résultat net de frais, dividendes perçus.
- **Backtest** : ce qu'auraient donné les règles depuis 2016, comparé à la référence et au hasard.
- **Paramètres** : seuils, frais, filtres personnels, mise à jour et qualité des données.
- **Méthodologie** : chaque règle expliquée simplement.
""")
