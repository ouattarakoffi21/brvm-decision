"""Assemblage des modules : du fichier de cours à la liste des décisions du jour.

Ordre des contrôles pour chaque titre (le premier échec écarte le titre) :
données fiables -> liquidité -> filtres personnels -> score -> tendance.
"""
from __future__ import annotations

import pandas as pd

from . import fondamental, liquidite, qualite, signaux
from .donnees import charger_sources, enregistrer_sqlite
from .filtres import (appliquer_filtres, lire_conformite_activite, lire_exclusions,
                      lire_fondamentaux_saisis)
from .risque import dimensionner, evaluer_portefeuille, lire_portefeuille

ORDRE_ACTIONS = ["VENDRE", "ALLÉGER", "ACHAT", "CONSERVER", "SURVEILLER", "NEUTRE", "ÉCARTÉ"]


def preparer_tout(cfg: dict) -> dict:
    """Étapes lourdes (lecture, contrôle qualité, matrices), mises en cache par l'application."""
    prep = qualite.preparer(charger_sources(cfg), cfg)
    mat = liquidite.construire_matrices(prep["cours"])
    prep["matrices"] = mat
    prep["liquidite"] = liquidite.liquidite(mat, cfg)
    prep["indicateurs"] = signaux.indicateurs(mat["rt"], cfg)
    try:  # base SQLite des données validées, consultable avec pandas ou un outil SQL
        enregistrer_sqlite(cfg, {k: prep[k] for k in ("cours", "dividendes", "evenements",
                                                       "anomalies", "referentiel")})
    except Exception:  # noqa: BLE001 - la base est un confort, pas une dépendance
        pass
    return prep


def decisions_du_jour(prep: dict, cfg: dict, portefeuille: pd.DataFrame | None = None,
                      exclusions: pd.DataFrame | None = None,
                      saisis: pd.DataFrame | None = None) -> dict:
    mat = prep["matrices"]
    date = mat["cloture"].index[-1]
    cloture = mat["cloture"].loc[date]
    cotes = cloture.dropna().index.tolist()
    div = prep["dividendes"]
    ref = prep["referentiel"].set_index("ticker")
    ptf = lire_portefeuille() if portefeuille is None else portefeuille
    excl = lire_exclusions() if exclusions is None else exclusions
    saisis = lire_fondamentaux_saisis() if saisis is None else saisis

    liq = liquidite.tableau_liquidite(prep["liquidite"], cfg, date)
    filt = appliquer_filtres(cotes, cloture, cfg, excl, lire_conformite_activite(cfg), saisis)
    premiere_annee = prep["cours"]["date"].min().year
    fond = fondamental.evaluer(div, cloture, date, cfg, premiere_annee, saisis, cotes)
    tend = signaux.tendance(prep["indicateurs"], mat["rt"], date)
    derniere_cotation = prep["cours"].groupby("ticker")["date"].max()
    suspendu = mat["suspendu"].loc[date]
    detenus = set(ptf["ticker"]) if len(ptf) else set()

    lignes = []
    for t in cotes:
        f, l, fi, te = fond.loc[t], liq.loc[t], filt.loc[t], tend.loc[t]
        raisons, action = [], None
        detenu = t in detenus
        # 1. données
        if (date - derniere_cotation[t]).days > cfg["qualite"]["fraicheur_max_jours"]:
            action, raisons = "ÉCARTÉ", ["plus de cotation récente"]
        elif suspendu.get(t, False):
            action, raisons = "ÉCARTÉ", ["saut de cours inexpliqué récent : titre suspendu "
                                         "le temps de vérifier (voir Qualité des données)"]
        # 2. liquidité (un titre détenu reste suivi pour pouvoir le vendre)
        elif not l["liquide"] and not detenu:
            action, raisons = "ÉCARTÉ", ["peu liquide : " + l["motif"]]
        # 3. filtres personnels
        elif not fi["admis"] and not detenu:
            action, raisons = "ÉCARTÉ", [fi["motif_filtre"]]
        if action is None:
            if detenu:
                pos = ptf[ptf["ticker"] == t].sort_values("date_achat").iloc[0]
                action, raisons = signaux.regles_sortie(pos, mat["rt"][t].dropna(), date, te,
                                                        f["score"], cfg)
                if not fi["admis"]:
                    action = "VENDRE"
                    raisons = [f"titre désormais exclu par tes filtres : {fi['motif_filtre']}"] + raisons
            else:
                action, raisons = signaux.decision_achat(f["score"], te, cfg)
                if f.get("dividende_non_couvert") is True:
                    raisons.append("attention : dividende supérieur au bénéfice (non couvert)")
        alerte = signaux.alerte_detachement(div, t, date, cfg["signaux"]["alerte_detachement_jours"])
        if alerte:
            raisons.append(alerte)
        lignes.append({
            "ticker": t, "societe": ref["nom"].get(t, ""), "secteur": ref["secteur"].get(t, ""),
            "action": action, "justification": " ; ".join(raisons),
            "cours": cloture[t], "score": f["score"], "couverture_score": f["couverture"],
            "rendement_12m": f["rendement"], "regularite": f["regularite"],
            "per": f.get("per"), "momentum_6m": te["momentum"],
            "montant_median_fcfa": l["montant_median_fcfa"], "liquide": l["liquide"],
            "conformite": fi["conformite"], "detenu": detenu,
        })
    tab = pd.DataFrame(lignes).set_index("ticker")
    tab["ordre"] = tab["action"].map({a: i for i, a in enumerate(ORDRE_ACTIONS)})
    tab = tab.sort_values(["ordre", "score"], ascending=[True, False]).drop(columns="ordre")

    # propositions d'achat dimensionnées
    investi = {}
    if len(ptf):
        val = evaluer_portefeuille(ptf, cloture, div, date, cfg)
        investi = val["valeur_fcfa"].groupby(level=0).sum().to_dict()
    places = max(cfg["risque"]["nombre_lignes_cible"] - len(detenus), 0)
    achats = tab[tab["action"] == "ACHAT"].head(places)
    taille = dimensionner(achats, cfg, investi, ref["secteur"]) if len(achats) else pd.DataFrame()

    avertissements = []
    nb_lignes = len(detenus) + int((taille.get("quantite", pd.Series(dtype=int)) > 0).sum())
    if nb_lignes < cfg["risque"]["nombre_lignes_min"]:
        avertissements.append(
            f"Diversification insuffisante : {nb_lignes} ligne(s) possible(s) aujourd'hui pour "
            f"un minimum de {cfg['risque']['nombre_lignes_min']}. Mieux vaut patienter que "
            "concentrer le capital sur trop peu de titres.")
    if cfg["filtres"]["conformite_islamique"]:
        avertissements.append(f"Filtre de conformité actif : {int(filt['admis'].sum())} titre(s) "
                              f"admis sur {len(filt)}.")
    return {"date": date, "tableau": tab, "achats": taille, "avertissements": avertissements,
            "fondamental": fond, "liquidite": liq, "filtres": filt, "tendance": tend}
