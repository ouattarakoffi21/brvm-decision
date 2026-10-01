import streamlit as st

from brvm import ui
from brvm.risque import taux_aller_retour

cfg = ui.page("Signaux du jour")
prep = ui.donnees(cfg)
ui.bandeau_donnees(prep)
res = ui.decisions(cfg)
tab = res["tableau"]

for a in res["avertissements"]:
    st.warning(a)

st.caption(f"Coût d'un aller-retour (achat puis vente) : environ "
           f"{taux_aller_retour(cfg):.1%} du montant. Un signal ne vaut que s'il "
           "promet nettement plus que ce coût.")


def afficher_achats() -> None:
    """Quantités proposées, calculées pour le capital indiqué dans les paramètres."""
    st.subheader("Achats proposés")
    st.caption(f"Calculés pour un capital de **{ui.fcfa(cfg['risque']['capital_fcfa'])}** et "
               f"{cfg['risque']['nombre_lignes_cible']} lignes visées : modifiable dans "
               "Paramètres > Stratégie.")
    achats = res["achats"]
    if achats is None or achats.empty:
        st.info("Aucun achat proposé aujourd'hui.")
        return
    a = achats[achats["quantite"] > 0].rename_axis("Titre")
    st.dataframe(a[["quantite", "cours", "montant_fcfa", "frais_estimes_fcfa", "ajustement"]],
                 width="stretch",
                 column_config={
                     "quantite": "Quantité",
                     "cours": st.column_config.NumberColumn("Cours", format="%.0f"),
                     "montant_fcfa": st.column_config.NumberColumn("Montant (FCFA)", format="%.0f"),
                     "frais_estimes_fcfa": st.column_config.NumberColumn("Frais estimés (FCFA)",
                                                                         format="%.0f"),
                     "ajustement": "Ajustement"})
    total = a["montant_fcfa"].sum() + a["frais_estimes_fcfa"].sum()
    st.markdown(f"Total à engager : **{ui.fcfa(total)}**.")
    for t, r in achats[achats["quantite"] == 0].iterrows():
        st.caption(f"{t} : {r['remarque']}")
    st.caption("Passe tes ordres avec un cours limite proche du dernier cours : la liquidité "
               "est faible et un ordre « au marché » peut s'exécuter loin de ce prix.")
    st.subheader("Détail des signaux d'achat")


onglets = st.tabs(["🔴🟠 Ventes", "🟢 Achats", "🔵 Conservés", "🟡 À surveiller",
                   "⚫ Écartés", "Tableau complet"])
for k, (onglet, actions) in enumerate(zip(onglets[:5], [["VENDRE", "ALLÉGER"], ["ACHAT"],
                                                        ["CONSERVER"], ["SURVEILLER"],
                                                        ["ÉCARTÉ"]])):
    with onglet:
        if k == 1:
            afficher_achats()
        sel = tab[tab["action"].isin(actions)]
        if sel.empty:
            st.info("Aucun titre dans cette catégorie aujourd'hui.")
        for t, r in sel.iterrows():
            ui.carte_signal(t, r)

with onglets[5]:
    vue = tab.copy()
    vue.insert(0, "signal", vue["action"].map(lambda a: f"{ui.COULEURS_ACTION[a]} {a}"))
    st.dataframe(
        vue[["signal", "societe", "cours", "score", "rendement_12m", "momentum_6m",
             "justification"]].rename_axis("Titre"),
        width="stretch",
        column_config={
            "signal": "Signal", "societe": "Société",
            "cours": st.column_config.NumberColumn("Cours", format="%.0f"),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100,
                                                     format="%.0f"),
            "rendement_12m": st.column_config.NumberColumn("Rendement 12 m", format="percent"),
            "momentum_6m": st.column_config.NumberColumn("Momentum 6 m", format="percent"),
            "justification": st.column_config.TextColumn("Pourquoi", width="large"),
        },
    )

st.caption(f"Décisions calculées sur les données du {res['date']:%d/%m/%Y}.")
