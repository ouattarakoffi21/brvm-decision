"""Rapport de recherche : top 10 adapté au profil et fiche détaillée par valeur."""
import copy
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from brvm import recherche, ui
from brvm.filtres import lire_fondamentaux_saisis
from brvm.risque import taux_aller_retour

cfg = ui.page("Rapport de recherche",
              "Les valeurs qui correspondent à ton profil, analysées comme dans une note de "
              "recherche : valorisation, croissance, dividende, risque et niveaux d'intervention.",
              rubrique="Recherche actions · BRVM")
prep = ui.donnees(cfg)
ui.bandeau_donnees(prep)


@st.cache_data(show_spinner="Analyse des comptes publiés et des cours...")
def _analyse(empreinte: str, cfg_json: str) -> tuple[pd.DataFrame, pd.Timestamp]:
    c = json.loads(cfg_json)
    res = ui.decisions(c)
    return recherche.analyser(ui.donnees(c), res, c, lire_fondamentaux_saisis()), res["date"]


cle = {k: v for k, v in cfg.items() if k != "profil"}  # changer de profil ne relance pas l'analyse
df, date = _analyse(ui._empreinte(cle), json.dumps(cle, default=str))

# ------------------------------------------------------------------ profil
profil = copy.deepcopy(cfg.get("profil", {"tolerance": "équilibré", "montant_fcfa": 500_000,
                                          "horizon_mois": 36, "secteurs": []}))
with st.container(border=True):
    st.markdown("**Ton profil d'investisseur**")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    profil["tolerance"] = c1.segmented_control(
        "Tolérance au risque", list(recherche.PONDERATIONS_PROFIL), default=profil["tolerance"],
        help="Prudent : dividendes solides et faible risque. Dynamique : croissance et tendance.",
    ) or profil["tolerance"]
    profil["montant_fcfa"] = int(c2.number_input("Montant à investir (FCFA)", min_value=10_000,
                                                 value=int(profil["montant_fcfa"]), step=50_000))
    profil["horizon_mois"] = c3.select_slider("Horizon", options=[6, 12, 24, 36, 60, 120],
                                              value=int(profil["horizon_mois"]),
                                              format_func=lambda m: f"{m} mois" if m < 24 else f"{m // 12} ans")
    secteurs = sorted(df["secteur"].dropna().unique()) if len(df) else []
    profil["secteurs"] = st.multiselect("Secteurs préférés", secteurs, placeholder="Tous les secteurs",
                                        default=[s for s in profil["secteurs"] if s in secteurs])
if profil != cfg.get("profil"):
    st.session_state["cfg"] = {**cfg, "profil": profil}
    cfg = st.session_state["cfg"]
st.caption("Pour garder ce profil après un redémarrage de l'application en ligne : "
           "Paramètres > Conserver mes réglages.")

forfait = cfg["frais"]["bourse_en_ligne_annuel_fcfa"] / profil["montant_fcfa"]
if forfait > 0.02:
    st.warning(f"Avec {ui.fcfa(profil['montant_fcfa'])}, le forfait de bourse en ligne coûte à lui "
               f"seul {ui.pct(forfait)} du capital par an, en plus d'environ "
               f"{ui.pct(taux_aller_retour(cfg))} par achat-revente. Moins de lignes, gardées "
               "plus longtemps, limitent cet effet.")
if profil["horizon_mois"] < 12:
    st.warning("Horizon de moins d'un an : les frais et les variations de court terme pèsent "
               "lourd. Les fourchettes ci-dessous portent sur 12 mois.")

top = recherche.selection_profil(df, profil, cfg)
if top.empty:
    st.error("Aucune valeur ne passe tes critères. Élargis les secteurs ou la tolérance au risque.")
    st.stop()

# ------------------------------------------------------------------ synthèse
st.subheader(f"Top {len(top)} pour un profil {profil['tolerance']}")
per_marche = df["per"].median()
ui.tuiles([
    {"label": "Valeurs retenues", "valeur": len(top), "ton": "indigo",
     "detail": f"sur {len(df)} analysées"},
    {"label": "Rendement du dividende moyen", "valeur": ui.pct(top["rendement_12m"].mean()),
     "ton": "buy", "detail": "12 derniers mois"},
    {"label": "PER médian du top", "valeur": f"{top['per'].median():.1f}".replace(".", ","),
     "ton": "ochre", "detail": f"marché : {per_marche:.1f}".replace(".", ",")},
    {"label": "Risque moyen", "valeur": f"{top['risque'].mean():.1f}/10".replace(".", ","),
     "ton": "watch", "detail": f"plafond du profil : {recherche.RISQUE_MAX[profil['tolerance']]:g}/10".replace(".", ",")},
])

vue = top.copy()
vue.insert(0, "rang", range(1, len(vue) + 1))
vue["signal"] = vue["action"].map(lambda a: f"{ui.COULEURS_ACTION[a]} {a}")
vue["fourchette"] = [f"{b:,.0f} – {h:,.0f}".replace(",", " ") if pd.notna(b) else "n.d."
                     for b, h in zip(vue["objectif_bas"], vue["objectif_haut"])]
vue["entree"] = [f"{b:,.0f} – {h:,.0f}".replace(",", " ") if pd.notna(b) else "n.d."
                 for b, h in zip(vue["entree_bas"], vue["entree_haut"])]
st.dataframe(
    vue[["rang", "societe", "signal", "cours", "per", "per_secteur", "tcam_ca", "rendement_12m",
         "soutenabilite", "solidite", "fourchette", "risque", "entree", "stop", "score_profil"]]
    .rename_axis("Titre"),
    width="stretch",
    column_config={
        "rang": st.column_config.NumberColumn("#", width="small"),
        "societe": "Société", "signal": "Signal",
        "cours": st.column_config.NumberColumn("Cours", format="%.0f"),
        "per": st.column_config.NumberColumn("PER", format="%.1f"),
        "per_secteur": st.column_config.NumberColumn("PER secteur", format="%.1f",
                                                     help="Médiane des PER du secteur à la BRVM"),
        "tcam_ca": st.column_config.NumberColumn("CA / an", format="percent",
                                                 help="Croissance annuelle moyenne du chiffre d'affaires"),
        "rendement_12m": st.column_config.NumberColumn("Dividende", format="percent"),
        "soutenabilite": st.column_config.ProgressColumn("Soutenabilité", min_value=0, max_value=10,
                                                         format="%.1f"),
        "solidite": "Solidité",
        "fourchette": "Fourchette 12 m",
        "risque": st.column_config.ProgressColumn("Risque", min_value=0, max_value=10, format="%.1f"),
        "entree": "Zone d'entrée",
        "stop": st.column_config.NumberColumn("Stop", format="%.0f"),
        "score_profil": st.column_config.ProgressColumn("Score profil", min_value=0, max_value=100,
                                                        format="%.0f"),
    },
)
st.download_button("Télécharger la synthèse (Excel)", recherche.synthese_excel(top, profil, date),
                   file_name=f"rapport_brvm_{date:%Y%m%d}.xlsx", icon=":material/download:")
st.caption("Les fourchettes reprennent les variations sur 12 mois observées depuis 2016, période "
           "qui inclut la baisse de 2017-2020 et la forte hausse depuis 2023. Ce ne sont pas des "
           "objectifs de cours.")


# ------------------------------------------------------------------ fiches
def fiche(t: str, r: pd.Series) -> None:
    ton = ui.TONS_ACTION[r["action"]]
    c = st.columns([1, 1, 1])
    per_txt = "n.s." if pd.isna(r["per"]) else f"{r['per']:.1f}".replace(".", ",")
    if pd.notna(r["per_vs_secteur"]):
        comp = f"{ui.pct(r['per_vs_secteur'], True)} vs secteur ({r['per_secteur']:.1f})".replace(".", ",", 1)
    else:
        comp = "comparaison sectorielle indisponible (moins de 3 pairs)"
    ui.tuiles([
        {"label": "PER", "valeur": per_txt, "ton": "indigo", "detail": comp},
        {"label": f"{r['libelle_ca']} / an", "valeur": ui.pct(r["tcam_ca"], True), "ton": "ochre",
         "detail": f"{r['ca_annees'][0]}-{r['ca_annees'][-1]}"},
        {"label": "Rendement du dividende", "valeur": ui.pct(r["rendement_12m"]), "ton": "buy",
         "detail": "soutenabilité " + ("n.d." if pd.isna(r["soutenabilite"]) else
                                       f"{r['soutenabilite']:.1f}/10".replace(".", ","))},
        {"label": "Risque", "valeur": f"{r['risque']:.1f}/10".replace(".", ","), "ton": ton,
         "detail": f"solidité {r['solidite']}"},
    ])
    g, d = st.columns([1.1, 1], gap="large")
    with g:
        fig = go.Figure()
        fig.add_bar(x=[str(a) for a in r["ca_annees"]], y=r["ca_serie"], name=r["libelle_ca"],
                    marker_color="#2B3A8C", hovertemplate="%{y:,.0f} M FCFA<extra></extra>")
        fig.update_layout(height=230, margin=dict(l=0, r=0, t=30, b=0), showlegend=False,
                          title=dict(text=f"{r['libelle_ca']} (millions FCFA)", font_size=13))
        st.plotly_chart(fig, width="stretch", key=f"ca_{t}", theme=None)
        dette = ("non pertinent pour une banque" if r["banque"] else
                 "n.d. (non publié par la source, saisissable dans Paramètres)"
                 if pd.isna(r["dette_cp"]) else f"{r['dette_cp']:.2f}".replace(".", ","))
        st.markdown(f"**Dette / capitaux propres** : {dette}")
        if pd.notna(r["per"]) and pd.notna(r["per_moyen_hist"]):
            st.markdown(f"**Valorisation** : {r['per']:.1f} fois les bénéfices aujourd'hui, contre "
                        f"{r['per_moyen_hist']:.1f} en moyenne en fin d'exercice sur les années "
                        "publiées.".replace(".", ",", 2))
    with d:
        st.markdown("**Fourchette à 12 mois** (historique, pas une prévision)")
        if pd.notna(r["objectif_bas"]):
            fig = go.Figure()
            fig.add_shape(type="line", x0=r["objectif_bas"], x1=r["objectif_haut"], y0=0, y1=0,
                          line=dict(color="#DCE1EA", width=14), layer="below")
            for x, nom, coul in [(r["objectif_bas"], "Scénario bas", "#BE3B26"),
                                 (r["cours"], "Cours", "#141B2D"),
                                 (r["objectif_haut"], "Scénario haut", "#1C8048")]:
                fig.add_scatter(x=[x], y=[0], mode="markers+text", text=[f"{x:,.0f}".replace(",", " ")],
                                textposition="top center", marker=dict(size=14, color=coul),
                                name=nom, hovertemplate=f"{nom} : %{{x:,.0f}}<extra></extra>")
            fig.update_layout(height=120, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
                              yaxis=dict(visible=False), xaxis=dict(showgrid=False))
            st.plotly_chart(fig, width="stretch", key=f"fourchette_{t}", theme=None)
            st.caption(f"Bas {ui.pct(r['potentiel_bas'], True)}, haut {ui.pct(r['potentiel_haut'], True)} : "
                       f"{r['methode_objectif']}.")
        else:
            st.caption(r["methode_objectif"])
        st.markdown(f"**Zone d'entrée** : {ui.fcfa(r['entree_bas'])} à {ui.fcfa(r['entree_haut'])}  \n"
                    f"**Stop-loss** : {ui.fcfa(r['stop'])}, puis relevé avec le plus haut atteint "
                    f"(stop suiveur de {cfg['signaux']['stop_suiveur']:.0%}).")
        st.caption("Zone d'entrée : du cours actuel jusqu'à une baisse d'un mois ordinaire pour ce "
                   "titre (ou jusqu'à sa moyenne 50 séances). Passe un ordre limité dans cette zone.")
    a, b, c = st.columns(3)
    with a:
        st.markdown("**Soutenabilité du dividende**")
        st.markdown("\n".join(f"- {x}" for x in r["raisons_soutenabilite"]))
    with b:
        st.markdown(f"**Solidité : {r['solidite']}**")
        st.markdown("\n".join(f"- {x}" for x in r["raisons_solidite"]) or "- aucun critère rempli")
    with c:
        st.markdown(f"**Risque {r['risque']:.1f}/10**".replace(".", ","))
        st.markdown("\n".join(f"- {x}" for x in r["raisons_risque"]))
    alerte = " Comptes anciens : le dernier exercice disponible n'est pas récent." if r["comptes_anciens"] else ""
    st.caption(f"Comptes : exercices {r['ca_annees'][0]}-{r['ca_annees'][-1]}, fiche société "
               f"Sikafinance relevée le 04/10/2026. Cours et dividendes : données validées de "
               f"l'application au {date:%d/%m/%Y}.{alerte}")


st.subheader("Fiches détaillées")
for i, (t, r) in enumerate(top.iterrows(), start=1):
    with st.expander(f"#{i}  {t} · {r['societe']} · {r['action']}", expanded=(i == 1)):
        fiche(t, r)

st.subheader("Analyser une autre valeur")
st.caption("Utile pour les titres que tu détiens déjà ou que tu envisages hors du top 10.")
detenus = [t for t in df.index if df.loc[t, "detenu"]]
choix = st.selectbox("Titre", df.index, index=df.index.get_loc(detenus[0]) if detenus else 0,
                     format_func=lambda x: f"{x} · {df.loc[x, 'societe']}" + (" (détenu)" if df.loc[x, "detenu"] else ""))
with st.container(border=True):
    fiche(choix, df.loc[choix])

with st.expander("Comment sont calculés ces indicateurs ?"):
    poids = recherche.PONDERATIONS_PROFIL[profil["tolerance"]]
    st.markdown(f"""
- **Comptes** : chiffre d'affaires, résultat net et dividende par action des 5 derniers exercices,
  repris des fiches société de Sikafinance. BNPA = résultat net / nombre de titres.
- **PER** = cours / dernier BNPA. Non significatif (n.s.) si le bénéfice est négatif ou si le PER
  dépasse 50. **PER secteur** : médiane des sociétés du même secteur (au moins 3).
- **Soutenabilité du dividende (sur 10)** : part du bénéfice distribuée (4 pts), régularité des
  versements (3 pts), tendance du résultat sur 3 exercices (2 pts), aucun exercice déficitaire (1 pt).
- **Solidité** (indicateur chiffré de l'avantage concurrentiel) : marge nette moyenne, constance
  des bénéfices, croissance du chiffre d'affaires et stabilité de la marge. 4 points ou plus = fort.
- **Risque (sur 10)** : volatilité sur 1 an (35 %), pire repli sur 3 ans (25 %), faible liquidité
  (20 %), fragilité des bénéfices (20 %), mesurés par rapport aux autres titres de la BRVM.
- **Fourchette à 12 mois** : variations sur 12 mois réellement observées pour ce titre sur 10 ans au plus
  (20e et 80e centiles), appliquées au cours actuel. Ce n'est pas un objectif de cours.
- **Zone d'entrée et stop** : du cours actuel jusqu'à une baisse mensuelle ordinaire ; stop au
  niveau du stop suiveur de la stratégie.
- **Top 10 du profil {profil['tolerance']}** : score combinant {", ".join(f"{k} {v} %" for k, v in poids.items())},
  après filtres (risque au plus {recherche.RISQUE_MAX[profil['tolerance']]:g}/10, secteurs choisis,
  liquidité suffisante pour revendre une ligne d'un dixième de ton montant en
  {cfg['liquidite']['seances_construction']} séances).
- **Dette / capitaux propres** : non publié par la source ; affiché seulement si tu saisis les
  états financiers (Paramètres > Fondamentaux).
""")
