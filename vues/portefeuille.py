import pandas as pd
import streamlit as st

from brvm import ui
from brvm.filtres import _secret
from brvm.risque import enregistrer_portefeuille, evaluer_portefeuille, lire_portefeuille

cfg = ui.page("Mon portefeuille")
prep = ui.donnees(cfg)
ui.bandeau_donnees(prep)

ptf = lire_portefeuille()
en_ligne = bool(_secret("portefeuille_csv"))

st.subheader("Mes positions")
if en_ligne:
    st.info("Positions lues depuis les secrets de l'application en ligne. Pour les modifier, "
            "édite le secret « portefeuille_csv » dans les réglages Streamlit Cloud.")
    st.dataframe(ptf, width="stretch", hide_index=True)
else:
    tickers = sorted(prep["cours"]["ticker"].unique())
    edite = st.data_editor(
        ptf, num_rows="dynamic", width="stretch", hide_index=True,
        column_config={
            "ticker": st.column_config.SelectboxColumn("Titre", options=tickers, required=True),
            "date_achat": st.column_config.DateColumn("Date d'achat", format="DD/MM/YYYY",
                                                      required=True),
            "quantite": st.column_config.NumberColumn("Quantité", min_value=1, step=1,
                                                      required=True),
            "prix_achat": st.column_config.NumberColumn("Prix d'achat unitaire", min_value=0,
                                                        required=True),
            "frais_achat": st.column_config.NumberColumn(
                "Frais d'achat réels (FCFA)",
                help="Lu sur l'avis d'opéré. Vide = estimation selon la grille Matha Securities."),
        })
    if st.button("Enregistrer mes positions", type="primary"):
        edite = edite.dropna(subset=["ticker", "date_achat", "quantite", "prix_achat"])
        edite["date_achat"] = pd.to_datetime(edite["date_achat"])
        enregistrer_portefeuille(edite)
        st.success("Positions enregistrées dans donnees_perso/portefeuille.csv (fichier local, "
                   "jamais publié).")
        st.rerun()
    with st.expander("Texte à copier dans les secrets pour l'application en ligne"):
        st.code(ptf.assign(date_achat=pd.to_datetime(ptf["date_achat"]).dt.strftime("%Y-%m-%d"))
                .to_csv(index=False), language="text")

if ptf.empty:
    st.info("Aucune position enregistrée.")
    st.stop()

mat = prep["matrices"]
date = mat["cloture"].index[-1]
val = evaluer_portefeuille(ptf, mat["cloture"].loc[date], prep["dividendes"], date, cfg)
res = ui.decisions(cfg)

c = st.columns(4)
c[0].metric("Valeur actuelle", ui.fcfa(val["valeur_fcfa"].sum()))
c[1].metric("Plus-value brute", ui.fcfa(val["plus_value_brute"].sum()))
c[2].metric("Dividendes perçus", ui.fcfa(val["dividendes_percus"].sum()))
c[3].metric("Résultat net si tout est vendu", ui.fcfa(val["resultat_net_si_vente"].sum()),
            help="Après frais d'achat, frais de vente estimés et droits de garde estimés")

val = val.join(res["tableau"][["action", "justification"]], how="left")
st.dataframe(val[["quantite", "prix_achat", "cours", "valeur_fcfa", "dividendes_percus",
                  "frais_totaux_estimes", "resultat_net_si_vente", "resultat_net_pct", "action",
                  "justification"]],
             width="stretch",
             column_config={
                 "quantite": "Qté", "prix_achat": st.column_config.NumberColumn("PRU", format="%.0f"),
                 "cours": st.column_config.NumberColumn("Cours", format="%.0f"),
                 "valeur_fcfa": st.column_config.NumberColumn("Valeur", format="%.0f"),
                 "dividendes_percus": st.column_config.NumberColumn("Dividendes", format="%.0f"),
                 "frais_totaux_estimes": st.column_config.NumberColumn("Frais", format="%.0f"),
                 "resultat_net_si_vente": st.column_config.NumberColumn("Résultat net",
                                                                        format="%.0f"),
                 "resultat_net_pct": st.column_config.NumberColumn("Résultat net %",
                                                                   format="percent"),
                 "action": "Signal", "justification": st.column_config.TextColumn(
                     "Pourquoi", width="large")})
if val["dividende_incertain"].any():
    st.caption("Au moins un dividende perçu a un montant non fiable dans les données : il n'est "
               "pas compté. Vérifie-le sur ton relevé Matha Securities.")

alertes = val[val["action"].isin(["VENDRE", "ALLÉGER"])]
for t, r in alertes.iterrows():
    st.error(f"{ui.COULEURS_ACTION[r['action']]} {r['action']} {t} : {r['justification']}")

secteur = prep["referentiel"].set_index("ticker")["secteur"]
rep = val.groupby(val.index.map(lambda x: secteur.get(x, "?")))["valeur_fcfa"].sum()
rep = rep / rep.sum()
st.subheader("Répartition par secteur")
st.bar_chart(rep)
depasse = rep[rep > cfg["risque"]["poids_max_secteur"]]
for s, p in depasse.items():
    st.warning(f"Secteur « {s} » à {p:.0%} du portefeuille, au-dessus du plafond de "
               f"{cfg['risque']['poids_max_secteur']:.0%}.")
