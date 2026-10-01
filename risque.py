"""Module 6 : frais, dimensionnement des positions et suivi du portefeuille."""
from __future__ import annotations

import io
import math

import numpy as np
import pandas as pd

from .filtres import DOSSIER_PERSO, _secret


# ---------------------------------------------------------------- frais
def commission_sgi(montant: float, cfg: dict) -> float:
    """Commission Matha Securities, tranches cumulatives."""
    plafonds = cfg["frais"]["sgi_tranches_plafond_fcfa"]
    taux = cfg["frais"]["sgi_tranches_taux"]
    reste, bas, total = montant, 0.0, 0.0
    for plafond, t in zip(plafonds + [math.inf], taux):
        tranche = min(reste, plafond - bas)
        if tranche <= 0:
            break
        total += tranche * t
        reste -= tranche
        bas = plafond
    return total


def frais_ordre(montant: float, cfg: dict) -> float:
    """Coût total d'un ordre d'achat ou de vente (SGI + marché + taxes estimées)."""
    f = cfg["frais"]
    return (commission_sgi(montant, cfg)
            + montant * (f["commission_brvm"] + f["commission_dcbr"]
                         + f["frais_complementaires_estimes"]))


def taux_aller_retour(cfg: dict, montant: float = 1_000_000) -> float:
    return 2 * frais_ordre(montant, cfg) / montant


# ---------------------------------------------------------------- dimensionnement
def dimensionner(candidats: pd.DataFrame, cfg: dict, deja_investi: dict | None = None,
                 secteurs: pd.Series | None = None) -> pd.DataFrame:
    """Répartit le capital entre les titres à acheter (classés par score décroissant).

    Contraintes : poids cible = 1 / nombre de lignes, plafond par ligne, par
    secteur, et part maximale du montant échangé médian (pour pouvoir revendre).
    """
    r = cfg["risque"]
    capital = r["capital_fcfa"]
    cible = min(1 / r["nombre_lignes_cible"], r["poids_max_ligne"])
    deja = deja_investi or {}
    expo_secteur = {}
    if secteurs is not None:
        for t, v in deja.items():
            s = secteurs.get(t, "?")
            expo_secteur[s] = expo_secteur.get(s, 0) + v
    lignes = []
    for t, c in candidats.sort_values("score", ascending=False).iterrows():
        s = secteurs.get(t, "?") if secteurs is not None else "?"
        budget = capital * cible - deja.get(t, 0)
        motif = []
        reste_secteur = capital * r["poids_max_secteur"] - expo_secteur.get(s, 0)
        if reste_secteur < budget:
            budget = max(reste_secteur, 0)
            motif.append("plafond sectoriel")
        plafond_liq = (cfg["liquidite"]["part_max_volume_journalier"]
                       * cfg["liquidite"]["seances_construction"]
                       * c.get("montant_median_fcfa", np.inf))
        if plafond_liq < budget:
            budget = plafond_liq
            motif.append("limité par la liquidité")
        # le budget doit couvrir les frais d'achat
        px = c["cours"]
        qte = int(budget / (px * (1 + taux_aller_retour(cfg) / 2))) if px > 0 else 0
        montant = qte * px
        frais = frais_ordre(montant, cfg) if qte else 0.0
        if qte:
            expo_secteur[s] = expo_secteur.get(s, 0) + montant
        remarque = "" if qte else (
            "rien à acheter : " + ", ".join(motif) + " atteint" if motif
            else "budget insuffisant pour une action")
        lignes.append((t, qte, px, montant, frais, "; ".join(motif), remarque))
    return pd.DataFrame(lignes, columns=["ticker", "quantite", "cours", "montant_fcfa",
                                         "frais_estimes_fcfa", "ajustement", "remarque"]
                        ).set_index("ticker")


# ---------------------------------------------------------------- portefeuille
COLONNES_PTF = ["ticker", "date_achat", "quantite", "prix_achat", "frais_achat"]


def lire_portefeuille() -> pd.DataFrame:
    """Positions réelles (secrets Streamlit en ligne, fichier local sinon)."""
    brut = _secret("portefeuille_csv")
    p = DOSSIER_PERSO / "portefeuille.csv"
    if brut:
        df = pd.read_csv(io.StringIO(brut))
    elif p.exists():
        df = pd.read_csv(p)
    else:
        vide = pd.DataFrame(columns=COLONNES_PTF)
        vide["date_achat"] = pd.to_datetime(vide["date_achat"])
        for col in ("quantite", "prix_achat", "frais_achat"):
            vide[col] = vide[col].astype(float)
        return vide
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["date_achat"] = pd.to_datetime(df["date_achat"], dayfirst=True)
    if "frais_achat" not in df.columns:
        df["frais_achat"] = np.nan
    return df[COLONNES_PTF]


def enregistrer_portefeuille(df: pd.DataFrame) -> None:
    DOSSIER_PERSO.mkdir(exist_ok=True)
    df.to_csv(DOSSIER_PERSO / "portefeuille.csv", index=False)


def evaluer_portefeuille(ptf: pd.DataFrame, cloture: pd.Series, div: pd.DataFrame,
                         date: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    """Valeur, plus-value latente nette de frais, dividendes perçus, droits de garde."""
    lignes = []
    for _, p in ptf.iterrows():
        t, q = p["ticker"], p["quantite"]
        px = cloture.get(t, np.nan)
        cout = q * p["prix_achat"]
        frais_a = p["frais_achat"] if pd.notna(p["frais_achat"]) else frais_ordre(cout, cfg)
        valeur = q * px
        frais_v = frais_ordre(valeur, cfg) if pd.notna(valeur) else np.nan
        d = div[(div["ticker"] == t) & (div["date_detachement"] > p["date_achat"])
                & (div["date_detachement"] <= date)]
        dividendes = q * d["montant_retenu"].sum()
        incertain = bool(d["montant_retenu"].isna().any())
        annees = max((date - p["date_achat"]).days, 0) / 365
        garde = valeur * cfg["frais"]["conservation_annuelle"] * annees
        pv_nette = valeur - frais_v - cout - frais_a + dividendes - garde
        lignes.append({
            "ticker": t, "quantite": q, "prix_achat": p["prix_achat"], "cours": px,
            "valeur_fcfa": valeur, "plus_value_brute": valeur - cout,
            "dividendes_percus": dividendes, "dividende_incertain": incertain,
            "frais_totaux_estimes": frais_a + frais_v + garde,
            "resultat_net_si_vente": pv_nette,
            "resultat_net_pct": pv_nette / (cout + frais_a) if cout else np.nan,
            "date_achat": p["date_achat"],
        })
    return pd.DataFrame(lignes).set_index("ticker") if lignes else pd.DataFrame()
