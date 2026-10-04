"""Séance en direct : cours du moment et signaux provisoires, sans attendre le soir."""
import pandas as pd
import streamlit as st

from brvm import direct, ui
from brvm.moteur import decisions_du_jour

cfg = ui.page("Séance en direct",
              "Les cours du moment et ce qu'ils changent aux signaux, sans attendre la mise à "
              "jour du soir.", rubrique="BRVM · en séance")
prep = ui.donnees(cfg)
officiel = ui.decisions(cfg)
zones, _ = ui.analyse_recherche(cfg)


@st.cache_data(ttl=120, show_spinner="Lecture des cours de la séance...")
def _cotations(referentiel: pd.DataFrame) -> pd.DataFrame:
    return direct.lire_cotations(referentiel)


st.markdown("Ces signaux sont **provisoires** : ils indiquent ce que diraient les règles si la "
            "séance fermait au cours affiché. Ce ne sont pas des prévisions. Les signaux "
            "officiels restent ceux de la page Signaux du jour, calculés sur les cours de clôture.")
auto = st.toggle("Actualiser automatiquement toutes les 3 minutes", value=False)


@st.fragment(run_every="3m" if auto else None)
def seance() -> None:
    if st.button("Actualiser maintenant", icon=":material/refresh:"):
        _cotations.clear()
    try:
        cot = _cotations(prep["referentiel"][["ticker", "nom"]])
    except Exception as e:  # noqa: BLE001 - source externe
        st.error(f"Impossible de lire les cours de la séance sur Sikafinance ({e}). "
                 "Réessaie dans quelques minutes ; les signaux officiels restent disponibles.")
        return
    en_cours, date_seance = direct.etat_marche()
    p2, c = direct.prep_avec_seance(prep, cot, date_seance, cfg)
    lu = pd.Timestamp(cot["lu_a"].iloc[0]).strftime("%H:%M")
    etat = "séance en cours" if en_cours else "marché fermé"
    st.markdown(f'<div class="fraicheur"><span class="dot"></span>Cours lus à <b>{lu}</b> '
                f'(heure d\'Abidjan)<span class="sep">·</span>{etat}<span class="sep">·</span>'
                f'séance du {date_seance:%d/%m/%Y}<span class="sep">·</span>source Sikafinance, '
                'léger différé possible</div>', unsafe_allow_html=True)

    if p2 is None:
        st.info(f"La séance du {date_seance:%d/%m/%Y} est déjà intégrée aux signaux officiels : "
                "rien de provisoire à calculer. Les cours ci-dessous sont ceux de cette séance.")
        prov = officiel["tableau"]
        al = pd.DataFrame(columns=["priorite", "ticker", "ton", "titre", "detail"])
    else:
        prov = decisions_du_jour(p2, cfg)["tableau"]
        al = direct.alertes(officiel["tableau"], prov, c, zones, cfg)

    var = c["variation"].dropna()
    ui.tuiles([
        {"label": "Titres en hausse", "valeur": int((var > 0.0005).sum()), "ton": "buy",
         "detail": f"plus forte : {ui.pct(var.max(), True)}" if len(var) else ""},
        {"label": "Titres en baisse", "valeur": int((var < -0.0005).sum()), "ton": "sell",
         "detail": f"plus forte : {ui.pct(var.min(), True)}" if len(var) else ""},
        {"label": "Titres en alerte", "valeur": al["ticker"].nunique(), "ton": "watch",
         "detail": "sur tes positions et les achats"},
        {"label": "Achats provisoires", "valeur": int((prov["action"] == "ACHAT").sum()),
         "ton": "indigo", "detail": f"officiels : {int((officiel['tableau']['action'] == 'ACHAT').sum())}"},
    ])

    st.subheader("Alertes de la séance")
    if al.empty:
        st.info("Aucune alerte : le cours du moment ne change aucun signal.")
    noms = prov["societe"].to_dict()
    # une carte par titre : l'alerte la plus urgente donne le titre et la couleur
    for i, (t, g) in enumerate(al.groupby("ticker", sort=False)):
        tete = g.iloc[0]
        details = [d if k == 0 else f"{ti} : {d}" for k, (ti, d) in enumerate(zip(g["titre"], g["detail"]))]
        ui.carte_alerte(t, tete["titre"], details, tete["ton"], str(noms.get(t, "")), delai=min(i, 10) * 60)

    st.subheader("Cours de la séance")
    vue = c.join(prov[["action", "detenu"]], how="left")
    vue["signal"] = vue["action"].map(lambda x: f"{ui.COULEURS_ACTION[x]} {x}" if pd.notna(x) else "")
    vue = vue.reindex(vue["variation"].abs().sort_values(ascending=False).index)
    seulement = st.toggle("Seulement mes positions et les achats", value=False)
    if seulement:
        vue = vue[vue["detenu"].fillna(False).astype(bool) | vue["action"].isin(["ACHAT"])]
    st.dataframe(
        vue[["nom", "signal", "dernier", "variation", "cloture_veille", "volume_fcfa",
             "volume_vs_mediane"]].rename_axis("Titre"),
        width="stretch",
        column_config={
            "nom": "Société", "signal": "Signal provisoire",
            "dernier": st.column_config.NumberColumn("Dernier", format="%.0f"),
            "variation": st.column_config.NumberColumn("Variation", format="percent"),
            "cloture_veille": st.column_config.NumberColumn("Clôture précédente", format="%.0f"),
            "volume_fcfa": st.column_config.NumberColumn("Échangé (FCFA)", format="%.0f"),
            "volume_vs_mediane": st.column_config.NumberColumn(
                "× habituel", format="%.1f", help="Montant échangé rapporté à la médiane des 60 "
                "dernières séances"),
        })
    st.caption("Sur la BRVM, un titre ne peut pas varier de plus d'environ 7,5 % par séance. "
               "Passe toujours des ordres à cours limité : avec peu d'échanges, un ordre au "
               "marché peut s'exécuter loin du dernier cours.")


seance()
