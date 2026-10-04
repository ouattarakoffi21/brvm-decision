"""Module 7 : backtest réaliste et comparaison au hasard.

Règles de simulation :
- décision à la clôture d'une date de révision, exécution à la clôture de
  la séance suivante (jamais au cours qui a servi à décider) ;
- un ordre n'est exécuté que si le titre a été échangé ce jour-là, et pour
  au plus une part du montant échangé ; sinon il est reporté quelques séances ;
- frais Matha Securities à l'achat et à la vente, droits de garde trimestriels,
  forfait annuel de bourse en ligne ;
- dividendes (montants validés) encaissés en liquidités au détachement ;
- nombres entiers d'actions.
Le score n'utilise que les dividendes connus à la date de décision.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import fondamental
from .filtres import appliquer_filtres
from .risque import frais_ordre


@dataclass
class Parametres:
    nom: str = "Stratégie complète"
    score_min: float = 60
    stop: float = 0.15
    utiliser_tendance: bool = True
    utiliser_score: bool = True
    aleatoire: bool = False
    tout_l_univers: bool = False   # référence : tous les titres admis, à poids égaux
    graine: int = 0
    objectif_gain: float | None = None  # allège la moitié de la ligne au-delà de ce gain
    part_allegee: float = 0.5


@dataclass
class Resultat:
    nom: str
    valeur: pd.Series
    operations: pd.DataFrame
    frais_totaux: float
    dividendes: float
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------- préparation
def dates_revision(cal: pd.DatetimeIndex, debut, fin, frequence: str) -> list:
    c = cal[(cal >= pd.Timestamp(debut)) & (cal <= pd.Timestamp(fin))]
    cle = c.to_period("Q" if frequence == "trimestrielle" else "M")
    return list(pd.Series(c, index=c).groupby(cle).first())


def contexte(prep: dict, cfg: dict, exclusions: pd.DataFrame | None = None,
             activite: pd.DataFrame | None = None) -> dict:
    """Pré-calcule tout ce qui ne dépend pas des paramètres testés (scores compris)."""
    mat = prep["matrices"]
    cal = mat["cloture"].index
    div_jour = prep["cours"].pivot(index="date", columns="ticker",
                                   values="dividende").reindex(cal).fillna(0.0)
    fin = cal[-1]
    revs = dates_revision(cal, cfg["backtest"]["debut"], fin, cfg["backtest"]["frequence"])
    premiere = prep["cours"]["date"].min().year
    excl = exclusions if exclusions is not None else pd.DataFrame(columns=["ticker", "motif"])
    act = activite if activite is not None else pd.DataFrame(columns=["ticker", "statut", "motif"])
    scores, eligibles = {}, {}
    for d in revs:
        px = mat["cloture"].loc[d].dropna()
        ok = (mat["cote"].loc[d] & ~mat["suspendu"].loc[d] & prep["liquidite"]["eligible"].loc[d])
        univers = [t for t in px.index if ok.get(t, False)]
        if univers:
            filt = appliquer_filtres(univers, px, cfg, excl, act, None)
            univers = [t for t in univers if filt.loc[t, "admis"]]
        eligibles[d] = univers
        scores[d] = (fondamental.evaluer(prep["dividendes"], px, d, cfg, premiere, None, univers)
                     ["score"] if univers else pd.Series(dtype=float))
    return {"cal": cal, "revisions": revs, "scores": scores, "eligibles": eligibles,
            "cloture": mat["cloture"], "rt": mat["rt"], "volume": mat["volume_fcfa"],
            "dividende": div_jour, "ind": prep["indicateurs"]}


# ---------------------------------------------------------------- simulation
def simuler(ctx: dict, cfg: dict, p: Parametres, debut=None, fin=None) -> Resultat:
    cal = ctx["cal"]
    debut = pd.Timestamp(debut or cfg["backtest"]["debut"])
    fin = pd.Timestamp(fin or cal[-1])
    jours = cal[(cal >= debut) & (cal <= fin)]
    revs = set(d for d in ctx["revisions"] if debut <= d <= fin)
    r, s, lq = cfg["risque"], cfg["signaux"], cfg["liquidite"]
    n_cible = r["nombre_lignes_cible"]
    rng = np.random.default_rng(p.graine)
    close, rt, vol, dvj = ctx["cloture"], ctx["rt"], ctx["volume"], ctx["dividende"]
    mm_c, mm_l, mom = ctx["ind"]["mm_courte"], ctx["ind"]["mm_longue"], ctx["ind"]["momentum"]

    cash = float(r["capital_fcfa"])
    pos = {}          # ticker -> dict(q, cout, date, pic)
    ordres = []       # dict(ticker, sens, montant_cible|q, age)
    ops, valeurs, investi = [], {}, {}
    frais_tot = div_tot = 0.0
    trimestre_prec = annee_prec = None

    def valeur_ptf(d):
        return cash + sum(v["q"] * close.at[d, t] for t, v in pos.items())

    for i, d in enumerate(jours):
        # 1. dividendes détachés ce jour
        for t, v in pos.items():
            m = dvj.at[d, t]
            if m > 0:
                cash += v["q"] * m
                div_tot += v["q"] * m
                v["div"] += v["q"] * m
        # 2. exécution des ordres de la veille (ventes d'abord)
        restants = []
        for o in sorted(ordres, key=lambda o: o["sens"] != "vente"):
            t = o["ticker"]
            px, v_jour = close.at[d, t], vol.at[d, t]
            if pd.isna(px) or not v_jour or v_jour <= 0:
                o["age"] += 1
                if o["age"] <= cfg["backtest"]["delai_execution_max"]:
                    restants.append(o)
                continue
            plafond = lq["part_max_volume_journalier"] * v_jour
            if o["sens"] == "vente" and t in pos:
                q = min(o.get("q", pos[t]["q"]), pos[t]["q"], int(plafond / px))
                if q <= 0:
                    o["age"] += 1
                    if o["age"] <= cfg["backtest"]["delai_execution_max"]:
                        restants.append(o)
                    continue
                montant = q * px
                f = frais_ordre(montant, cfg)
                cash += montant - f
                frais_tot += f
                v = pos[t]
                part = q / v["q"]
                gain = montant - f + v["div"] * part - v["cout"] * part
                ops.append((d, t, "vente", q, px, f, gain, o["motif"]))
                v["q"] -= q
                v["cout"] *= (1 - part)
                v["div"] *= (1 - part)
                if "q" in o:
                    o["q"] -= q
                if v["q"] == 0:
                    del pos[t]
                elif o.get("q", 1) <= 0:
                    pass  # allègement terminé
                else:
                    o["age"] += 1
                    restants.append(o)
            elif o["sens"] == "achat" and (t not in pos or o.get("suite")):
                budget = min(o["montant"], cash, plafond)
                q = int(budget / (px * 1.02))
                if q <= 0:
                    continue
                montant = q * px
                f = frais_ordre(montant, cfg)
                if montant + f > cash:
                    continue
                cash -= montant + f
                frais_tot += f
                if t in pos:
                    pos[t]["q"] += q
                    pos[t]["cout"] += montant + f
                else:
                    pos[t] = {"q": q, "cout": montant + f, "date": d, "pic": rt.at[d, t],
                              "div": 0.0, "rt0": rt.at[d, t], "allege": False}
                ops.append((d, t, "achat", q, px, f, np.nan, o["motif"]))
                # ligne construite en plusieurs séances si la liquidité l'impose
                o["montant"] -= montant + f
                o["age"] += 1
                o["suite"] = True
                if (o["montant"] > px * 1.02
                        and o["age"] <= cfg["liquidite"]["seances_construction"]):
                    restants.append(o)
        ordres = restants
        # 3. droits de garde (trimestre) et forfait bourse en ligne (année)
        tri = (d.year, (d.month - 1) // 3)
        if trimestre_prec is not None and tri != trimestre_prec:
            g = (valeur_ptf(d) - cash) * cfg["frais"]["conservation_annuelle"] / 4
            cash -= g
            frais_tot += g
        if annee_prec is not None and d.year != annee_prec:
            cash -= cfg["frais"]["bourse_en_ligne_annuel_fcfa"]
            frais_tot += cfg["frais"]["bourse_en_ligne_annuel_fcfa"]
        trimestre_prec, annee_prec = tri, d.year
        # 4. stop suiveur quotidien (sur rendement total)
        en_vente = {o["ticker"] for o in ordres if o["sens"] == "vente"}
        for t, v in pos.items():
            x = rt.at[d, t]
            if pd.notna(x):
                v["pic"] = max(v["pic"], x)
                if x / v["pic"] - 1 <= -p.stop and t not in en_vente:
                    ordres.append({"ticker": t, "sens": "vente", "age": 0, "motif": "stop"})
        # 5. révision : sorties puis entrées
        if d in revs:
            elig = ctx["eligibles"].get(d, [])
            sc = ctx["scores"].get(d, pd.Series(dtype=float))
            if p.aleatoire:
                sc = pd.Series(rng.random(len(elig)) * 100, index=elig)
            en_vente = {o["ticker"] for o in ordres if o["sens"] == "vente"}
            for t in list(pos):
                if t in en_vente:
                    continue
                motif = None
                if t not in elig:
                    motif = "sorti de l'univers (liquidité ou suspension)"
                elif p.utiliser_score and not p.aleatoire and sc.get(t, np.nan) < s["score_sortie"]:
                    motif = "score dégradé"
                elif p.utiliser_tendance and mm_c.at[d, t] < mm_l.at[d, t]:
                    motif = "retournement"
                if motif:
                    ordres.append({"ticker": t, "sens": "vente", "age": 0, "motif": motif})
                elif (p.objectif_gain is not None and not pos[t]["allege"]
                      and rt.at[d, t] / pos[t]["rt0"] - 1 >= p.objectif_gain):
                    q = int(pos[t]["q"] * p.part_allegee)
                    if q > 0:
                        pos[t]["allege"] = True
                        ordres.append({"ticker": t, "sens": "vente", "age": 0, "q": q,
                                       "motif": "objectif de gain"})
            partants = {o["ticker"] for o in ordres if o["sens"] == "vente"}
            cible = len(elig) if p.tout_l_univers else n_cible
            places = cible - (len(pos) - len(partants & set(pos)))
            if places > 0:
                cand = sc.dropna()
                if p.utiliser_score and not p.aleatoire:
                    cand = cand[cand >= p.score_min]
                if p.utiliser_tendance:
                    cand = cand[[(mm_c.at[d, t] > mm_l.at[d, t]) and (mom.at[d, t] > 0)
                                 for t in cand.index]]
                cand = cand[[t not in pos for t in cand.index]].sort_values(ascending=False)
                total = valeur_ptf(d)
                for t in cand.index[:places]:
                    ordres.append({"ticker": t, "sens": "achat", "age": 0,
                                   "montant": total * (1 / max(cible, 1) if p.tout_l_univers
                                                       else min(1 / n_cible, r["poids_max_ligne"])),
                                   "motif": "entrée"})
        valeurs[d] = valeur_ptf(d)
        investi[d] = 1 - cash / valeurs[d] if valeurs[d] else 0.0

    val = pd.Series(valeurs)
    ops_df = pd.DataFrame(ops, columns=["date", "ticker", "sens", "quantite", "cours",
                                        "frais", "gain_net", "motif"])
    res = Resultat(p.nom, val, ops_df, frais_tot, div_tot)
    res.stats = statistiques(res, cfg)
    res.stats["part_investie_moyenne"] = float(pd.Series(investi).mean())
    return res


def reference_equiponderee(ctx: dict, cfg: dict, debut=None, fin=None) -> Resultat:
    """Tous les titres liquides et admis, à poids égaux, révision annuelle.

    Même univers, mêmes frais et mêmes contraintes de liquidité que la stratégie.
    """
    ctx2 = dict(ctx)
    ctx2["revisions"] = [d for d in ctx["revisions"] if d.month <= 3]
    p = Parametres(nom="Référence : tous les titres liquides", stop=10.0,
                   utiliser_tendance=False, utiliser_score=False, tout_l_univers=True)
    return simuler(ctx2, cfg, p, debut, fin)


def statistiques(res: Resultat, cfg: dict) -> dict:
    v = res.valeur
    if len(v) < 2:
        return {}
    annees = (v.index[-1] - v.index[0]).days / 365.25
    cagr = (v.iloc[-1] / v.iloc[0]) ** (1 / annees) - 1 if annees > 0 else np.nan
    dd = (v / v.cummax() - 1).min()
    rq = v.pct_change().dropna()
    ventes = res.operations[res.operations["sens"] == "vente"]
    return {
        "rendement_annualise": cagr,
        "perte_maximale": dd,
        "volatilite_annuelle": rq.std() * np.sqrt(250),
        "nombre_operations": len(res.operations),
        "taux_reussite": (ventes["gain_net"] > 0).mean() if len(ventes) else np.nan,
        "frais_totaux_fcfa": res.frais_totaux,
        "dividendes_encaisses_fcfa": res.dividendes,
        "valeur_finale_fcfa": v.iloc[-1],
    }


def comparer_hasard(ctx: dict, cfg: dict, p: Parametres, debut=None, fin=None,
                    tirages: int | None = None) -> tuple[pd.Series, float]:
    """Rendements annualisés de portefeuilles tirés au hasard (même univers, mêmes règles).

    Renvoie la distribution et la part des tirages battus par la stratégie.
    """
    n = tirages or cfg["backtest"]["tirages_hasard"]
    graine = cfg["backtest"]["graine"]
    strat = simuler(ctx, cfg, p, debut, fin).stats["rendement_annualise"]
    distrib = []
    for k in range(n):
        q = Parametres(nom="hasard", stop=p.stop, utiliser_tendance=False,
                       utiliser_score=False, aleatoire=True, graine=graine + k)
        distrib.append(simuler(ctx, cfg, q, debut, fin).stats["rendement_annualise"])
    distrib = pd.Series(distrib)
    return distrib, float((distrib < strat).mean())


def optimiser(ctx: dict, cfg: dict, grille: dict | None = None) -> pd.DataFrame:
    """Petite grille testée UNIQUEMENT sur la période d'optimisation.

    Critère : rendement annualisé / perte maximale (ratio de Calmar).
    Grille volontairement réduite pour limiter le sur-ajustement.
    """
    grille = grille or {"score_min": [50, 60, 70], "stop": [0.10, 0.15, 0.20]}
    fin_opt = cfg["backtest"]["fin_optimisation"]
    lignes = []
    for sm in grille["score_min"]:
        for st_ in grille["stop"]:
            r = simuler(ctx, cfg, Parametres(score_min=sm, stop=st_), fin=fin_opt).stats
            calmar = (r["rendement_annualise"] / abs(r["perte_maximale"])
                      if r["perte_maximale"] else np.nan)
            lignes.append({"score_min": sm, "stop": st_, **r, "calmar": calmar})
    return pd.DataFrame(lignes).sort_values("calmar", ascending=False)


def indice_reference(prep: dict, debut, fin) -> pd.Series | None:
    """BRVM Composite importé (indice de prix), rebasé ; None s'il n'a pas été importé."""
    ind = prep.get("indice")
    if ind is None or ind.empty:
        return None
    s = ind.set_index("date")["valeur"].sort_index()
    s = s[(s.index >= pd.Timestamp(debut)) & (s.index <= pd.Timestamp(fin))]
    return s / s.iloc[0] if len(s) else None
