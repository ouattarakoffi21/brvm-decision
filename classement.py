import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from brvm import ui

cfg = ui.page("Classement des titres")
prep = ui.donnees(cfg)
ui.bandeau_donnees(prep)
res = ui.decisions(cfg)
tab = res["tableau"].sort_values("score", ascending=False)

st.dataframe(
    tab[["societe", "secteur", "action", "score", "couverture_score", "rendement_12m",
         "regularite", "per", "momentum_6m", "montant_median_fcfa", "conformite"]],
    width="stretch",
    column_config={
        "societe": "Société", "secteur": "Secteur", "action": "Signal",
        "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
        "couverture_score": st.column_config.NumberColumn(
            "Critères disponibles", format="percent",
            help="Part des critères pondérés disponibles pour ce titre"),
        "rendement_12m": st.column_config.NumberColumn("Rendement 12 m", format="percent"),
        "regularite": st.column_config.NumberColumn("Régularité", format="percent",
                                                    help="Années avec dividende sur 5"),
        "per": st.column_config.NumberColumn("PER", format="%.1f"),
        "momentum_6m": st.column_config.NumberColumn("Momentum 6 m", format="percent"),
        "montant_median_fcfa": st.column_config.NumberColumn("Échangé / séance (FCFA)",
                                                             format="%.0f"),
        "conformite": "Conformité islamique"},
)
st.caption("Le PER n'apparaît que pour les sociétés dont tu as saisi les états financiers "
           "(Paramètres > Fondamentaux).")

st.subheader("Fiche d'un titre")
t = st.selectbox("Titre", tab.index, format_func=lambda x: f"{x} · {tab.loc[x, 'societe']}")
r = tab.loc[t]
st.markdown(f"**{ui.COULEURS_ACTION[r['action']]} {r['action']}** : {r['justification']}")

mat, ind = prep["matrices"], prep["indicateurs"]
periode = st.radio("Période", ["1 an", "3 ans", "Tout"], horizontal=True)
debut = mat["cloture"].index[-1] - pd.DateOffset(years={"1 an": 1, "3 ans": 3}.get(periode, 30))
f = mat["cloture"].index >= debut
fig = go.Figure()
fig.add_scatter(x=mat["rt"].index[f], y=mat["rt"][t][f], name="Rendement total (base 100)")
fig.add_scatter(x=ind["mm_courte"].index[f], y=ind["mm_courte"][t][f],
                name=f"Moyenne {cfg['signaux']['mm_courte']} séances", line=dict(dash="dot"))
fig.add_scatter(x=ind["mm_longue"].index[f], y=ind["mm_longue"][t][f],
                name=f"Moyenne {cfg['signaux']['mm_longue']} séances", line=dict(dash="dash"))
fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10),
                  legend=dict(orientation="h", y=-0.2))
st.plotly_chart(fig, width="stretch")

fig2 = go.Figure()
fig2.add_scatter(x=mat["cloture"].index[f], y=mat["cloture"][t][f], name="Cours (ajusté des divisions)")
fig2.update_layout(height=260, margin=dict(l=10, r=10, t=30, b=10), title="Cours")
st.plotly_chart(fig2, width="stretch")

d = prep["dividendes"]
d = d[d["ticker"] == t].sort_values("date_detachement", ascending=False)
st.markdown("**Dividendes** (montant retenu après contrôle)")
st.dataframe(d[["date_detachement", "exercice", "montant", "montant_retenu", "statut"]],
             width="stretch", hide_index=True,
             column_config={"date_detachement": st.column_config.DateColumn("Détachement"),
                            "exercice": st.column_config.NumberColumn("Exercice", format="%d"),
                            "montant": st.column_config.NumberColumn("Montant archive", format="%.0f"),
                            "montant_retenu": st.column_config.NumberColumn("Montant retenu",
                                                                            format="%.0f"),
                            "statut": "Contrôle"})
anom = prep["anomalies"]
anom = anom[anom["ticker"] == t]
if len(anom):
    with st.expander(f"Anomalies de données sur {t} ({len(anom)})"):
        st.dataframe(anom, width="stretch", hide_index=True)
