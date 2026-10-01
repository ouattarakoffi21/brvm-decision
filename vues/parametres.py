from datetime import date

import pandas as pd
import streamlit as st

from brvm import ui
from brvm.config import chemin, fusionner, sauvegarder_config
from brvm.donnees import lire_fichier, mettre_a_jour, modele_fondamentaux
from brvm.filtres import DOSSIER_PERSO, _secret, lire_exclusions
from brvm.risque import lire_portefeuille, taux_aller_retour

cfg = ui.page("Paramètres")
onglets = st.tabs(["Stratégie", "Frais", "Filtres personnels", "Données", "Qualité des données"])

# ------------------------------------------------------------------ stratégie
with onglets[0]:
    with st.form("strategie"):
        c1, c2 = st.columns(2)
        capital = c1.number_input("Capital (FCFA)", 100_000, 10_000_000_000,
                                  int(cfg["risque"]["capital_fcfa"]), step=100_000)
        lignes = c2.number_input("Nombre de lignes visé", 3, 20,
                                 int(cfg["risque"]["nombre_lignes_cible"]))
        mini = c1.number_input("Nombre de lignes minimal", 2, 20,
                               int(cfg["risque"]["nombre_lignes_min"]))
        pmax = c2.slider("Poids maximal par ligne", 0.05, 0.50,
                         float(cfg["risque"]["poids_max_ligne"]), 0.05)
        smax = c1.slider("Poids maximal par secteur", 0.20, 1.00,
                         float(cfg["risque"]["poids_max_secteur"]), 0.05)
        score = c2.slider("Score minimal pour acheter", 30, 90,
                          int(cfg["signaux"]["score_achat_min"]), 5)
        sortie = c1.slider("Score en dessous duquel vendre", 10, 60,
                           int(cfg["signaux"]["score_sortie"]), 5)
        stop = c2.slider("Stop suiveur (repli depuis le plus haut)", 0.05, 0.40,
                         float(cfg["signaux"]["stop_suiveur"]), 0.01)
        objectif = c1.slider("Objectif de gain (alléger au-delà)", 0.10, 1.50,
                             float(cfg["signaux"]["objectif_gain"]), 0.05)
        liq = c2.number_input("Montant médian échangé minimal par séance (FCFA)", 0, 100_000_000,
                              int(cfg["liquidite"]["montant_median_min_fcfa"]), step=250_000)
        st.markdown("**Pondérations du score**")
        p = st.columns(5)
        poids = {k: p[i].number_input(lbl, 0.0, 1.0, float(cfg["fondamental"][k]), 0.05)
                 for i, (k, lbl) in enumerate([
                     ("poids_rendement", "Rendement"), ("poids_regularite", "Régularité"),
                     ("poids_per", "PER"), ("poids_distribution", "Distribution"),
                     ("poids_endettement", "Endettement")])}
        ok = st.form_submit_button("Appliquer", type="primary")
    if ok:
        st.session_state["cfg"] = fusionner(cfg, {
            "risque": {"capital_fcfa": capital, "nombre_lignes_cible": lignes,
                       "nombre_lignes_min": mini, "poids_max_ligne": pmax,
                       "poids_max_secteur": smax},
            "signaux": {"score_achat_min": score, "score_sortie": sortie, "stop_suiveur": stop,
                        "objectif_gain": objectif},
            "liquidite": {"montant_median_min_fcfa": liq},
            "fondamental": poids})
        st.success("Paramètres appliqués pour cette session.")
        st.rerun()

# ------------------------------------------------------------------ frais
with onglets[1]:
    f = cfg["frais"]
    st.markdown(f"""
Grille **Matha Securities** (conditions générales de tarification) : commission de
**0,80 %** jusqu'à 500 millions FCFA par transaction, 0,60 % de 500 millions à 1,5 milliard,
0,40 % au-delà ; conservation **0,25 % par an** prélevée chaque trimestre ; bourse en ligne
**10 000 FCFA par an**.

S'y ajoutent les commissions de marché publiées par la BRVM (BRVM 0,20 %, DC/BR 0,10 %) et
les taxes, estimées ici à **{f['frais_complementaires_estimes']:.2%}**. Remplace cette
estimation par le taux lu sur ton premier avis d'opéré.
""")
    with st.form("frais"):
        comp = st.number_input("Taxes et frais complémentaires par ordre (%)", 0.0, 2.0,
                               f["frais_complementaires_estimes"] * 100, 0.05) / 100
        ok = st.form_submit_button("Appliquer")
    if ok:
        st.session_state["cfg"] = fusionner(cfg, {"frais": {"frais_complementaires_estimes": comp}})
        st.rerun()
    st.metric("Coût estimé d'un aller-retour (achat + vente)", f"{taux_aller_retour(cfg):.2%}")

# ------------------------------------------------------------------ filtres
with onglets[2]:
    st.markdown("**Conformité islamique**")
    actif = st.toggle("Activer le filtre", cfg["filtres"]["conformite_islamique"])
    mode = st.radio("Mode", ["sectoriel", "strict"],
                    index=0 if cfg["filtres"]["mode_conformite"] == "sectoriel" else 1,
                    captions=["Exclut les activités non conformes (banque et assurance "
                              "conventionnelles, alcool, tabac, jeux).",
                              "Exige en plus les trois ratios AAOIFI, calculés à partir des "
                              "états financiers que tu as saisis."], horizontal=True)
    if (actif, mode) != (cfg["filtres"]["conformite_islamique"], cfg["filtres"]["mode_conformite"]):
        st.session_state["cfg"] = fusionner(cfg, {"filtres": {"conformite_islamique": actif,
                                                              "mode_conformite": mode}})
        st.rerun()
    st.caption("La liste des activités se modifie dans donnees/manuel/conformite_activite.csv.")

    st.markdown("**Exclusions déontologiques** (clients audités, conflits d'intérêts)")
    excl = lire_exclusions()
    if _secret("exclusions_csv"):
        st.info("Liste lue depuis les secrets de l'application en ligne.")
        st.dataframe(excl, hide_index=True)
    else:
        e = st.data_editor(excl, num_rows="dynamic", hide_index=True, width="stretch",
                           column_config={"ticker": "Titre", "motif": "Motif (facultatif)"})
        if st.button("Enregistrer les exclusions"):
            DOSSIER_PERSO.mkdir(exist_ok=True)
            e.dropna(subset=["ticker"]).to_csv(DOSSIER_PERSO / "exclusions.csv", index=False)
            st.success("Enregistré dans donnees_perso/exclusions.csv (local, jamais publié).")
            st.rerun()

    st.markdown("**États financiers saisis** (PER, distribution, endettement, ratios AAOIFI)")
    p = modele_fondamentaux()
    st.download_button("Télécharger le fichier de saisie", p.read_bytes(),
                       file_name="fondamentaux_saisis.xlsx")
    envoi = st.file_uploader("Renvoyer le fichier rempli", type=["xlsx"], key="fond")
    if envoi is not None:
        df = pd.read_excel(envoi)
        df.to_excel(p, index=False)
        st.success(f"{len(df)} ligne(s) enregistrée(s).")

# ------------------------------------------------------------------ données
with onglets[3]:
    prep = ui.donnees(cfg)
    ui.bandeau_donnees(prep)
    if st.button("Mettre à jour les données", type="primary"):
        with st.spinner("Téléchargement de l'archive, puis Sikafinance si nécessaire..."):
            rapport = mettre_a_jour(cfg)
        st.json(rapport)
        st.cache_data.clear()
        st.rerun()
    st.markdown("**Import manuel** (export Sikafinance, fichier Excel personnel...)")
    type_f = st.radio("Contenu du fichier", ["Cours d'un ou plusieurs titres",
                                             "Historique du BRVM Composite"], horizontal=True)
    code = st.text_input("Code du titre, si le fichier n'a pas de colonne titre (ex. SNTS)")
    envoi = st.file_uploader("Fichier CSV ou Excel", type=["csv", "xlsx", "xls"], key="cours")
    if envoi is not None:
        try:
            defaut = "BRVMC" if type_f.startswith("Historique") else (code.upper() or None)
            df = lire_fichier(envoi, defaut)
            st.dataframe(df.head(), hide_index=True)
            prefixe = "indice" if type_f.startswith("Historique") else "cours"
            if st.button(f"Enregistrer ces {len(df)} lignes"):
                dossier = chemin(cfg, "dossier_manuel")
                dossier.mkdir(parents=True, exist_ok=True)
                df.to_csv(dossier / f"{prefixe}_import_{date.today():%Y%m%d_%H%M%S}.csv",
                          index=False)
                st.cache_data.clear()
                st.success("Importé. Les fichiers manuels priment sur l'archive.")
        except ValueError as err:
            st.error(str(err))

# ------------------------------------------------------------------ qualité
with onglets[4]:
    prep = ui.donnees(cfg)
    a = prep["anomalies"]
    st.markdown(f"**{len(a)} point(s) signalé(s)** par le contrôle qualité.")
    types = st.multiselect("Types", sorted(a["type"].unique()),
                           default=[t for t in ["saut inexpliqué", "division probable",
                                                "dividende à vérifier", "données périmées"]
                                    if t in set(a["type"])])
    st.dataframe(a[a["type"].isin(types)], width="stretch", hide_index=True)
    st.markdown("""
**Corriger à la main** : ajoute une ligne dans `donnees/manuel/evenements_manuels.csv`
(colonnes `ticker,date,type,facteur,commentaire`) avec pour type :
`division` (et le facteur, ex. 2), `erreur` (séance écartée) ou `ignorer` (saut réel, pas de
suspension). Pour un dividende, ajoute la ligne corrigée dans
`donnees/manuel/dividendes_manuels.csv` (colonnes `ticker,date_detachement,montant,exercice`).
""")

st.divider()
st.subheader("Conserver mes réglages")
en_ligne = _secret("portefeuille_csv") is not None or _secret("exclusions_csv") is not None
st.markdown("""
**En ligne**, tout ce qui est enregistré dans l'application est effacé au redémarrage du
serveur. Pour garder tes réglages, copie le texte ci-dessous **à la fin** de tes Secrets
(« Gérer l'application », puis Settings, puis Secrets), sous la ligne du mot de passe.
""")
texte = ui.texte_secrets_config(st.session_state["cfg"])
excl_txt = lire_exclusions()
ptf_txt = lire_portefeuille()
perso = []
if len(excl_txt):
    perso.append('exclusions_csv = """' + excl_txt.to_csv(index=False) + '"""')
if len(ptf_txt):
    ptf_txt = ptf_txt.assign(date_achat=pd.to_datetime(ptf_txt["date_achat"]).dt.strftime("%Y-%m-%d"))
    perso.append('portefeuille_csv = """' + ptf_txt.to_csv(index=False) + '"""')
if perso:
    texte = "[perso]\n" + "\n".join(perso) + "\n\n" + texte
st.code(texte or "# Aucun réglage modifié : rien à copier.", language="toml")
st.caption("Le mot de passe doit rester sur la toute première ligne des Secrets, au-dessus de ce "
           "texte. Si une section [perso] existe déjà dans tes Secrets, remplace-la par celle-ci.")
if not en_ligne and st.button("Enregistrer tous les paramètres dans config.toml (usage local)"):
    sauvegarder_config(st.session_state["cfg"])
    st.success("config.toml mis à jour sur cet ordinateur.")
