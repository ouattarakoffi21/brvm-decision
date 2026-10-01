"""Module 2 : matrices de marché et filtre de liquidité.

La liquidité se mesure en montant échangé (FCFA) et en régularité des
échanges : sur la BRVM, presque tous les titres cotent chaque jour, mais
parfois pour quelques milliers de francs seulement.
"""
from __future__ import annotations

import pandas as pd


def construire_matrices(cours: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Tableaux dates x tickers utilisés par tous les modules.

    Un jour de séance sans ligne pour un titre coté compte comme « aucun
    échange » (volume 0, dernier cours reporté). Hors période de cotation : vide.
    """
    cal = pd.DatetimeIndex(sorted(cours["date"].unique()))
    cloture = cours.pivot(index="date", columns="ticker", values="cloture").reindex(cal)
    rt = cours.pivot(index="date", columns="ticker", values="indice_rt").reindex(cal)
    vol = cours.pivot(index="date", columns="ticker", values="volume_fcfa").reindex(cal)
    susp = cours.pivot(index="date", columns="ticker", values="suspendu").reindex(cal)

    premiere = cours.groupby("ticker")["date"].min()
    derniere = cours.groupby("ticker")["date"].max()
    cote = pd.DataFrame({t: (cal >= premiere[t]) & (cal <= derniere[t]) for t in cloture.columns},
                        index=cal)
    cloture = cloture.ffill().where(cote)
    rt = rt.ffill().where(cote)
    vol = vol.fillna(0.0).where(cote)
    susp = susp.astype("boolean").fillna(False).astype(bool) & cote
    return {"cloture": cloture, "rt": rt, "volume_fcfa": vol, "suspendu": susp, "cote": cote}


def liquidite(mat: dict, cfg: dict) -> dict[str, pd.DataFrame]:
    """Montant médian échangé et part des séances actives, en glissant."""
    n = cfg["liquidite"]["fenetre_seances"]
    vol = mat["volume_fcfa"]
    mediane = vol.rolling(n, min_periods=n).median()
    part = (vol > 0).astype(float).where(vol.notna()).rolling(n, min_periods=n).mean()
    eligible = ((mediane >= cfg["liquidite"]["montant_median_min_fcfa"])
                & (part >= cfg["liquidite"]["part_seances_min"]))
    return {"mediane_fcfa": mediane, "part_seances": part, "eligible": eligible}


def tableau_liquidite(liq: dict, cfg: dict, date: pd.Timestamp | None = None) -> pd.DataFrame:
    """Photo de la liquidité à une date (dernière séance par défaut), avec motif."""
    date = date or liq["mediane_fcfa"].index[-1]
    l = cfg["liquidite"]
    df = pd.DataFrame({
        "montant_median_fcfa": liq["mediane_fcfa"].loc[date],
        "part_seances": liq["part_seances"].loc[date],
        "liquide": liq["eligible"].loc[date],
    })
    motif = []
    for t, r in df.iterrows():
        if pd.isna(r["montant_median_fcfa"]):
            motif.append(f"historique inférieur à {l['fenetre_seances']} séances")
        elif r["montant_median_fcfa"] < l["montant_median_min_fcfa"]:
            motif.append(f"montant médian {r['montant_median_fcfa'] / 1e6:.1f} M FCFA "
                         f"< {l['montant_median_min_fcfa'] / 1e6:.1f} M")
        elif r["part_seances"] < l["part_seances_min"]:
            motif.append(f"échangé {r['part_seances']:.0%} des séances "
                         f"< {l['part_seances_min']:.0%}")
        else:
            motif.append("")
    df["motif"] = motif
    return df
