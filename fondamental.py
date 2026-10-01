"""Module 3 : sélection fondamentale et score composite.

Critères obligatoires (disponibles pour tous les titres, calculés à partir
de l'historique des dividendes) : rendement sur 12 mois et régularité.
Critères optionnels (issus des états financiers saisis dans
donnees_perso/fondamentaux_saisis.xlsx) : PER, taux de distribution, endettement.

Chaque critère est converti en rang centile (0 à 100) parmi les titres
comparables ; le score est la moyenne pondérée des critères disponibles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CRITERES = {  # nom -> (clé de pondération, sens : +1 plus haut = mieux)
    "rendement": ("poids_rendement", +1),
    "regularite": ("poids_regularite", +1),
    "per": ("poids_per", -1),
    "distribution": ("poids_distribution", -1),
    "endettement": ("poids_endettement", -1),
}
OBLIGATOIRES = ("rendement", "regularite")


def rendement_12m(div: pd.DataFrame, cloture: pd.Series, date: pd.Timestamp) -> pd.Series:
    """Dividendes détachés sur 12 mois / cours du jour.

    Si un dividende de la période est non fiable, le rendement est inconnu (NaN).
    Un titre sans aucun détachement sur 12 mois a un rendement de 0.
    """
    fen = div[(div["date_detachement"] > date - pd.Timedelta(days=365))
              & (div["date_detachement"] <= date)]
    out = {}
    for t, px in cloture.items():
        if pd.isna(px):
            out[t] = np.nan
            continue
        lignes = fen[fen["ticker"] == t]
        out[t] = np.nan if lignes["montant_retenu"].isna().any() \
            else lignes["montant_retenu"].sum() / px
    return pd.Series(out, dtype=float)


def regularite(div: pd.DataFrame, tickers, date: pd.Timestamp, annees: int,
               premiere_annee: int) -> pd.Series:
    """Part des années civiles complètes récentes avec au moins un détachement.

    Un détachement compte même si son montant est non fiable : le versement a eu lieu.
    Moins de 2 années d'historique : inconnu.
    """
    fin = date.year - 1
    debut = max(fin - annees + 1, premiere_annee)
    n = fin - debut + 1
    if n < 2:
        return pd.Series(np.nan, index=list(tickers))
    d = div[(div["date_detachement"].dt.year >= debut) & (div["date_detachement"].dt.year <= fin)]
    ans = d.groupby("ticker")["date_detachement"].apply(lambda s: s.dt.year.nunique())
    return pd.Series({t: ans.get(t, 0) / n for t in tickers}, dtype=float)


def ratios_saisis(saisis: pd.DataFrame, cloture: pd.Series, div: pd.DataFrame,
                  date: pd.Timestamp) -> pd.DataFrame:
    """PER, taux de distribution et endettement du dernier exercice saisi et publié."""
    cols = ["per", "distribution", "endettement", "capitalisation", "exercice_saisi"]
    if saisis is None or saisis.empty:
        return pd.DataFrame(columns=cols)
    s = saisis.copy()
    s["exercice"] = pd.to_numeric(s["exercice"], errors="coerce")
    # un exercice N n'est connu qu'après publication (on retient le 30 juin N+1)
    s = s[s["exercice"] + 1 < date.year + (date.month > 6)]
    s = s.sort_values("exercice").groupby("ticker").last()
    lignes = {}
    for t, r in s.iterrows():
        px = cloture.get(t, np.nan)
        bpa = r["benefice_net"] / r["nombre_titres"] if r.get("nombre_titres") else np.nan
        dpa = div[(div["ticker"] == t) & (pd.to_numeric(div["exercice"], errors="coerce")
                                          == r["exercice"])]["montant_retenu"].sum(min_count=1)
        lignes[t] = {
            "per": px / bpa if bpa and bpa > 0 else np.nan,
            "distribution": dpa / bpa if bpa and bpa > 0 and pd.notna(dpa) else np.nan,
            "endettement": (r["dettes_financieres"] / r["capitaux_propres"]
                            if r.get("capitaux_propres") else np.nan),
            "capitalisation": px * r["nombre_titres"] if r.get("nombre_titres") else np.nan,
            "exercice_saisi": int(r["exercice"]),
        }
    return pd.DataFrame.from_dict(lignes, orient="index", columns=cols)


def score_composite(criteres: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Rangs centiles pondérés, renormalisés sur les critères disponibles."""
    f = cfg["fondamental"]
    df = criteres.copy()
    poids_total = sum(f[k] for k, _ in CRITERES.values())
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for nom, (cle, sens) in CRITERES.items():
        if nom not in df.columns:
            continue
        rang = (sens * df[nom]).rank(pct=True) * 100
        df[f"rang_{nom}"] = rang.round(0)
        present = rang.notna()
        num[present] += f[cle] * rang[present]
        den[present] += f[cle]
    df["score"] = (num / den.replace(0, np.nan)).round(1)
    df["couverture"] = (den / poids_total).round(2)
    manque = df[list(OBLIGATOIRES)].isna().any(axis=1)
    df.loc[manque, "score"] = np.nan
    if "distribution" in df.columns:
        df["dividende_non_couvert"] = df["distribution"] > f["distribution_max"]
    return df


def evaluer(div: pd.DataFrame, cloture_jour: pd.Series, date: pd.Timestamp,
            cfg: dict, premiere_annee: int, saisis: pd.DataFrame | None = None,
            univers: list | None = None) -> pd.DataFrame:
    """Tableau complet des critères et du score pour un univers de titres à une date."""
    px = cloture_jour if univers is None else cloture_jour.reindex(univers)
    crit = pd.DataFrame({
        "cours": px,
        "rendement": rendement_12m(div, px, date),
        "regularite": regularite(div, px.index, date, cfg["fondamental"]["annees_regularite"],
                                 premiere_annee),
    })
    ratios = ratios_saisis(saisis, px, div, date)
    crit = crit.join(ratios, how="left")
    return score_composite(crit, cfg)
