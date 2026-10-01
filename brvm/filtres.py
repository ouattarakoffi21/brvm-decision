"""Module 5 : filtres personnels (conformité islamique, exclusions déontologiques).

Les données personnelles sont lues, dans l'ordre :
1. les « secrets » Streamlit (application en ligne) ;
2. les fichiers du dossier donnees_perso (usage local, jamais publié).
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from .config import RACINE, chemin

DOSSIER_PERSO = RACINE / "donnees_perso"


def _secret(cle: str):
    try:
        import streamlit as st
        return st.secrets.get("perso", {}).get(cle)
    except Exception:  # noqa: BLE001 - hors Streamlit ou sans secrets
        return None


def lire_exclusions() -> pd.DataFrame:
    """Sociétés exclues (clients audités, conflits d'intérêts). Colonnes : ticker, motif."""
    brut = _secret("exclusions_csv")
    if brut:
        df = pd.read_csv(io.StringIO(brut))
    elif (DOSSIER_PERSO / "exclusions.csv").exists():
        df = pd.read_csv(DOSSIER_PERSO / "exclusions.csv")
    else:
        df = pd.DataFrame(columns=["ticker", "motif"])
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    return df


def lire_fondamentaux_saisis() -> pd.DataFrame:
    p = DOSSIER_PERSO / "fondamentaux_saisis.xlsx"
    return pd.read_excel(p) if p.exists() else pd.DataFrame()


def lire_conformite_activite(cfg: dict) -> pd.DataFrame:
    p = chemin(cfg, "dossier_manuel") / "conformite_activite.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["ticker", "statut", "motif"])


def ratios_aaoifi(saisis: pd.DataFrame, cloture: pd.Series) -> pd.DataFrame:
    """Trois ratios AAOIFI du dernier exercice saisi.

    Dettes / capitalisation, trésorerie placée à intérêt / capitalisation,
    revenus non conformes / chiffre d'affaires.
    """
    if saisis is None or saisis.empty:
        return pd.DataFrame(columns=["ratio_dettes", "ratio_tresorerie", "ratio_revenus"])
    s = saisis.sort_values("exercice").groupby("ticker").last()
    capi = cloture.reindex(s.index) * s["nombre_titres"]
    return pd.DataFrame({
        "ratio_dettes": s["dettes_financieres"] / capi,
        "ratio_tresorerie": s["tresorerie_et_placements_a_interet"] / capi,
        "ratio_revenus": s["revenus_non_conformes"] / s["chiffre_affaires"],
    })


def appliquer_filtres(tickers, cloture: pd.Series, cfg: dict,
                      exclusions: pd.DataFrame, activite: pd.DataFrame,
                      saisis: pd.DataFrame | None) -> pd.DataFrame:
    """Pour chaque titre : admis (bool), statut de conformité et motif d'exclusion."""
    f = cfg["filtres"]
    excl = dict(zip(exclusions["ticker"], exclusions.get("motif", "")))
    act = activite.set_index("ticker") if len(activite) else pd.DataFrame()
    ratios = ratios_aaoifi(saisis, cloture)
    lignes = []
    for t in tickers:
        admis, motif, conformite = True, "", ""
        if t in excl:
            admis = False
            motif = f"exclusion déontologique : {excl[t] or 'sans motif précisé'}"
        # statut de conformité (calculé même si le filtre est désactivé, pour affichage)
        statut_act = act.loc[t, "statut"] if t in act.index else "admissible a priori"
        motif_act = act.loc[t, "motif"] if t in act.index else ""
        if statut_act == "non conforme":
            conformite = f"non conforme : {motif_act}"
        elif t in ratios.index and ratios.loc[t].notna().all():
            r = ratios.loc[t]
            depasse = [n for n, v, s in [
                ("dettes", r["ratio_dettes"], f["ratio_dettes_max"]),
                ("trésorerie à intérêt", r["ratio_tresorerie"], f["ratio_tresorerie_interet_max"]),
                ("revenus non conformes", r["ratio_revenus"], f["ratio_revenus_non_conformes_max"]),
            ] if v > s]
            conformite = ("non conforme : ratio " + ", ".join(depasse) + " au-dessus du seuil AAOIFI"
                          if depasse else "conforme (activité et ratios AAOIFI vérifiés)")
        else:
            conformite = ("à vérifier : " + motif_act if statut_act == "à vérifier"
                          else "activité admissible a priori, ratios AAOIFI non vérifiés")
        if admis and f["conformite_islamique"]:
            if conformite.startswith("non conforme"):
                admis, motif = False, conformite
            elif f["mode_conformite"] == "strict" and not conformite.startswith("conforme"):
                admis, motif = False, "mode strict : " + conformite
        lignes.append((t, admis, conformite, motif))
    return pd.DataFrame(lignes, columns=["ticker", "admis", "conformite", "motif_filtre"]
                        ).set_index("ticker")


def nombre_restants(filtres: pd.DataFrame) -> int:
    return int(np.sum(filtres["admis"]))
