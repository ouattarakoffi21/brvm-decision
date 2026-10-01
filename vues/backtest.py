import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from brvm import backtest as bt
from brvm import ui
from brvm.filtres import lire_conformite_activite, lire_exclusions

cfg = ui.page("Backtest")
prep = ui.donnees(cfg)
ui.bandeau_donnees(prep)

st.markdown("""
Les règles sont rejouées sur l'historique, **frais Matha Securities, dividendes et liquidité
réelle compris**. La période est coupée en deux : les paramètres sont choisis sur la
première (optimisation), puis jugés sur la seconde (test), qu'ils n'ont jamais « vue ».
La stratégie est aussi comparée à des portefeuilles tirés **au hasard** dans le même univers :
si elle ne fait pas mieux que le hasard, elle n'apporte rien.
""")
fin_opt = pd.Timestamp(cfg["backtest"]["fin_optimisation"])
debut_test = fin_opt + pd.Timedelta(days=1)
tirages = st.slider("Nombre de portefeuilles tirés au hasard", 20, 300,
                    cfg["backtest"]["tirages_hasard"], step=20,
                    help="Plus il y en a, plus la comparaison est solide (et plus c'est long).")


@st.cache_data(show_spinner=False)
def lancer(cfg_json: str, empreinte: str, tirages: int) -> dict:
    c = json.loads(cfg_json)
    ctx = bt.contexte(ui.donnees(c), c, lire_exclusions(), lire_conformite_activite(c))
    progres = st.progress(0.0, "Optimisation sur la première période...")
    opt = bt.optimiser(ctx, c)
    b = opt.iloc[0]
    choisi = bt.Parametres(nom="Stratégie (paramètres optimisés)", score_min=float(b["score_min"]),
                           stop=float(b["stop"]))
    progres.progress(0.2, "Simulations complètes...")
    complet = bt.simuler(ctx, c, choisi)
    ref = bt.reference_equiponderee(ctx, c)
    test = bt.simuler(ctx, c, choisi, debut=debut_test)
    ref_test = bt.reference_equiponderee(ctx, c, debut=debut_test)
    distrib = []
    for k in range(tirages):
        q = bt.Parametres(nom="hasard", stop=choisi.stop, utiliser_tendance=False,
                          utiliser_score=False, aleatoire=True, graine=c["backtest"]["graine"] + k)
        distrib.append(bt.simuler(ctx, c, q, debut=debut_test).stats["rendement_annualise"])
        progres.progress(0.3 + 0.7 * (k + 1) / tirages,
                         f"Portefeuilles au hasard : {k + 1}/{tirages}")
    progres.empty()
    return {"opt": opt, "choisi": (choisi.score_min, choisi.stop), "complet": complet,
            "ref": ref, "test": test, "ref_test": ref_test, "hasard": pd.Series(distrib)}


if st.button("Lancer le backtest", type="primary") or "bt_ok" in st.session_state:
    st.session_state["bt_ok"] = True
    r = lancer(json.dumps(cfg, default=str), ui._empreinte(cfg), tirages)
    test, ref_test, hasard = r["test"], r["ref_test"], r["hasard"]
    part = float((hasard < test.stats["rendement_annualise"]).mean())

    st.subheader("Verdict sur la période de test")
    st.caption(f"Du {test.valeur.index[0]:%d/%m/%Y} au {test.valeur.index[-1]:%d/%m/%Y}, avec "
               f"les paramètres retenus sur la période d'optimisation : score minimum "
               f"{r['choisi'][0]:.0f}, stop suiveur {r['choisi'][1]:.0%}. Capital simulé : "
               f"{ui.fcfa(cfg['risque']['capital_fcfa'])} (frais fixes compris : plus le capital "
               "est petit, plus ils pèsent).")
    c = st.columns(3)
    c[0].metric("Stratégie, rendement annualisé", ui.pct(test.stats["rendement_annualise"]),
                ui.points(test.stats["rendement_annualise"] - ref_test.stats["rendement_annualise"])
                + " vs référence")
    c[1].metric("Référence (tous les titres liquides)", ui.pct(ref_test.stats["rendement_annualise"]))
    c[2].metric("Portefeuilles au hasard battus", f"{part * 100:.0f} %")
    if part >= 0.9:
        st.success(f"La stratégie fait mieux que {part * 100:.0f} % des portefeuilles tirés au "
                   "hasard sur la période de test.")
    elif part >= 0.5:
        st.info("La stratégie fait mieux que la moitié des tirages au hasard, sans s'en "
                "détacher nettement : l'avantage n'est pas démontré.")
    else:
        st.error("La stratégie fait moins bien que la majorité des portefeuilles tirés au "
                 "hasard sur la période de test. Sur cette période, elle n'apporte pas de "
                 "rendement supplémentaire.")
    dd_s, dd_r = test.stats["perte_maximale"], ref_test.stats["perte_maximale"]
    st.markdown(f"Perte maximale : **{ui.pct(dd_s)}** pour la stratégie, **{ui.pct(dd_r)}** "
                f"pour la référence. Part moyenne du capital investie : "
                f"**{ui.pct(test.stats['part_investie_moyenne'])}** (le reste en liquidités, "
                "sans rémunération dans la simulation).")

    fig = go.Figure()
    fig.add_histogram(x=hasard, nbinsx=30, name="Portefeuilles au hasard")
    fig.add_vline(x=test.stats["rendement_annualise"], line_color="green",
                  annotation_text="Stratégie")
    fig.add_vline(x=ref_test.stats["rendement_annualise"], line_color="gray", line_dash="dash",
                  annotation_text="Référence")
    fig.update_layout(height=300, xaxis_tickformat=".0%", margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_title="Rendement annualisé sur la période de test")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Toute la période")
    fig = go.Figure()
    for res, nom, coul in [(r["complet"], "Stratégie", "#1F6F43"),
                           (r["ref"], "Référence", "#9AA0A6")]:
        fig.add_scatter(x=res.valeur.index, y=res.valeur / res.valeur.iloc[0] * 100, name=nom,
                        line=dict(color=coul))
    indice = bt.indice_reference(prep, r["complet"].valeur.index[0], r["complet"].valeur.index[-1])
    if indice is not None:
        fig.add_scatter(x=indice.index, y=indice * 100, name="BRVM Composite (indice de prix)")
    else:
        st.caption("Pour ajouter le BRVM Composite, importe son historique dans Paramètres.")
    fig.add_vline(x=fin_opt, line_dash="dot", annotation_text="début du test")
    fig.update_layout(height=380, yaxis_title="Base 100", margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")

    lignes = {}
    for res, nom in [(r["complet"], "Stratégie, tout"), (r["ref"], "Référence, tout"),
                     (test, "Stratégie, test"), (ref_test, "Référence, test")]:
        lignes[nom] = res.stats
    s = pd.DataFrame(lignes).T
    st.dataframe(s, width="stretch", column_config={
        "rendement_annualise": st.column_config.NumberColumn("Rendement annualisé", format="percent"),
        "perte_maximale": st.column_config.NumberColumn("Perte maximale", format="percent"),
        "volatilite_annuelle": st.column_config.NumberColumn("Volatilité", format="percent"),
        "nombre_operations": st.column_config.NumberColumn("Opérations", format="%d"),
        "taux_reussite": st.column_config.NumberColumn("Ventes gagnantes", format="percent"),
        "frais_totaux_fcfa": st.column_config.NumberColumn("Frais (FCFA)", format="%.0f"),
        "dividendes_encaisses_fcfa": st.column_config.NumberColumn("Dividendes (FCFA)",
                                                                   format="%.0f"),
        "valeur_finale_fcfa": st.column_config.NumberColumn("Valeur finale (FCFA)", format="%.0f"),
        "part_investie_moyenne": st.column_config.NumberColumn("Part investie", format="percent")})

    with st.expander("Grille testée sur la période d'optimisation"):
        st.dataframe(r["opt"][["score_min", "stop", "rendement_annualise", "perte_maximale",
                               "calmar", "nombre_operations"]], width="stretch",
                     hide_index=True)
    with st.expander("Journal des opérations de la stratégie"):
        st.dataframe(r["complet"].operations, width="stretch", hide_index=True)
    st.caption("Limites : les montants de dividendes jugés non fiables ne sont pas comptés "
               "(résultat plutôt sous-estimé) ; la correction des dividendes utilise des montants "
               "Sikafinance publiés après coup ; les liquidités ne sont pas rémunérées ; "
               "la conformité par ratios AAOIFI n'est pas rejouée faute d'historique.")
