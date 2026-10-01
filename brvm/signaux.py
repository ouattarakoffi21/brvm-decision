"""Module 4 : signaux de marché (quand acheter, quand vendre).

Tous les indicateurs sont calculés sur l'indice de rendement total
(dividendes réintégrés) : un détachement ne déclenche donc jamais, à lui
seul, un faux signal de baisse ou un stop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def indicateurs(rt: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    s = cfg["signaux"]
    return {
        "mm_courte": rt.rolling(s["mm_courte"], min_periods=s["mm_courte"]).mean(),
        "mm_longue": rt.rolling(s["mm_longue"], min_periods=s["mm_longue"]).mean(),
        "momentum": rt / rt.shift(s["momentum_seances"]) - 1,
    }


def tendance(ind: dict, rt: pd.DataFrame, date) -> pd.DataFrame:
    """État de tendance de chaque titre à une date."""
    mc, ml, mo = (ind["mm_courte"].loc[date], ind["mm_longue"].loc[date],
                  ind["momentum"].loc[date])
    px = rt.loc[date]
    return pd.DataFrame({
        "mm_courte": mc, "mm_longue": ml, "momentum": mo,
        "haussiere": (mc > ml) & (px > ml),
        "retournement": mc < ml,
    })


def regles_sortie(position: pd.Series, rt_serie: pd.Series, date, tend: pd.Series,
                  score: float, cfg: dict) -> tuple[str, list[str]]:
    """Décision sur un titre détenu : VENDRE, ALLÉGER ou CONSERVER, avec les raisons."""
    s = cfg["signaux"]
    depuis = rt_serie[(rt_serie.index >= position["date_achat"]) & (rt_serie.index <= date)]
    raisons = []
    if len(depuis) < 2:
        return "CONSERVER", ["achat trop récent pour juger"]
    perf = depuis.iloc[-1] / depuis.iloc[0] - 1
    repli = depuis.iloc[-1] / depuis.max() - 1
    if repli <= -s["stop_suiveur"]:
        raisons.append(f"stop atteint : {repli:.0%} depuis le plus haut atteint pendant la détention "
                       f"(seuil {-s['stop_suiveur']:.0%})")
    if bool(tend.get("retournement", False)):
        raisons.append("retournement de tendance : moyenne courte passée sous la moyenne longue")
    if pd.notna(score) and score < s["score_sortie"]:
        raisons.append(f"score fondamental dégradé : {score:.0f} < {s['score_sortie']}")
    if raisons:
        return "VENDRE", raisons + [f"performance depuis l'achat, dividendes compris : {perf:+.1%}"]
    if perf >= s["objectif_gain"]:
        return "ALLÉGER", [f"objectif de gain atteint : {perf:+.1%} (seuil {s['objectif_gain']:.0%}) ; "
                           "prendre une partie du bénéfice"]
    return "CONSERVER", [f"performance depuis l'achat, dividendes compris : {perf:+.1%}",
                         f"repli depuis le plus haut : {repli:.0%}"]


def alerte_detachement(div: pd.DataFrame, ticker: str, date, jours: int) -> str:
    """Détachement annoncé dans les prochains jours : vendre avant ferait perdre le dividende."""
    a_venir = div[(div["ticker"] == ticker) & (div["date_detachement"] > date)
                  & (div["date_detachement"] <= date + pd.Timedelta(days=jours))]
    if a_venir.empty:
        return ""
    r = a_venir.iloc[0]
    m = f"{r['montant_retenu']:.0f} FCFA" if pd.notna(r["montant_retenu"]) else "montant non fiable"
    return (f"détachement prévu le {r['date_detachement']:%d/%m/%Y} ({m}) : "
            f"vendre avant cette date ferait perdre le dividende")


def decision_achat(score: float, tend: pd.Series, cfg: dict) -> tuple[str, list[str]]:
    s = cfg["signaux"]
    if pd.isna(score):
        return "ÉCARTÉ", ["score non calculable (donnée obligatoire manquante)"]
    if score < s["score_achat_min"]:
        return "NEUTRE", [f"score {score:.0f} < seuil d'achat {s['score_achat_min']}"]
    mo = tend.get("momentum", np.nan)
    if pd.isna(tend.get("mm_longue", np.nan)) or pd.isna(mo):
        return "SURVEILLER", ["historique trop court pour mesurer la tendance"]
    if bool(tend["haussiere"]) and mo > 0:
        return "ACHAT", [f"score {score:.0f} ≥ {s['score_achat_min']}",
                         "tendance haussière : moyenne courte au-dessus de la longue",
                         f"momentum 6 mois dividendes compris : {mo:+.1%}"]
    return "SURVEILLER", [f"score {score:.0f} ≥ {s['score_achat_min']}",
                          f"mais tendance pas encore favorable (momentum {mo:+.1%})"]
