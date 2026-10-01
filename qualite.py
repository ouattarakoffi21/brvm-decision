"""Module 1 (suite) : contrôle qualité, corrections et cours ajustés.

Sur la BRVM, la variation d'un cours en une séance est plafonnée. Un saut
plus grand que ce plafond vient donc :
- d'une erreur de saisie (le cours revient à son niveau quelques séances après) ;
- d'une division ou d'un regroupement du nominal (rapport proche d'un entier) ;
- d'un événement non identifié (augmentation de capital, droits...).
Les deux premiers cas sont corrigés automatiquement ; le troisième suspend
le titre et est signalé pour vérification manuelle.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- dividendes
def rattacher_dividendes(cours: pd.DataFrame, div: pd.DataFrame) -> pd.Series:
    """Montant de dividende détaché à chaque séance (0 sinon).

    Un détachement tombant un jour sans séance est rattaché à la séance suivante.
    """
    montant = pd.Series(0.0, index=cours.index)
    if div.empty:
        return montant
    for t, d in div.groupby("ticker"):
        lignes = cours.index[cours["ticker"] == t]
        if len(lignes) == 0:
            continue
        dates = cours.loc[lignes, "date"].to_numpy()
        pos = np.searchsorted(dates, d["date_detachement"].to_numpy())
        for p, m in zip(pos, d["montant"].to_numpy()):
            if p < len(lignes) and pd.notna(m):
                montant.loc[lignes[p]] += float(m)
    return montant


# ---------------------------------------------------------------- détection
def _entier_proche(rapport: float, tolerance: float) -> int | None:
    n = round(rapport)
    return n if n >= 2 and abs(rapport / n - 1) <= tolerance else None


def detecter_evenements(cours: pd.DataFrame, div: pd.DataFrame, cfg: dict,
                        manuels: pd.DataFrame | None = None
                        ) -> tuple[pd.DataFrame, pd.Series]:
    """Repère les sauts anormaux. Renvoie (événements, masque des lignes invalides)."""
    q = cfg["qualite"]
    seuil, k, tol = q["seuil_saut"], q["fenetre_retour"], q["tolerance_division"]
    manuels = manuels if manuels is not None else pd.DataFrame()
    cles_manuelles = {}
    if len(manuels):
        for _, m in manuels.iterrows():
            cles_manuelles[(m["ticker"], pd.Timestamp(m["date"]))] = m

    # Détection sur le cours seul : au détachement, le plafond de variation
    # empêche le cours de chuter de plus de ~7,5 %, donc pas de faux signal.
    invalide = pd.Series(False, index=cours.index)
    evts = []

    for t, g in cours.groupby("ticker", sort=False):
        idx = g.index.to_numpy()
        px = g["cloture"].to_numpy(dtype=float)
        dt = g["date"].to_numpy()
        i_prec = 0
        i = 1
        while i < len(idx):
            if np.isnan(px[i]) or px[i] <= 0:
                invalide.loc[idx[i]] = True
                i += 1
                continue
            prec = px[i_prec]
            r = px[i] / prec - 1
            cle = (t, pd.Timestamp(dt[i]))
            if cle in cles_manuelles:
                m = cles_manuelles[cle]
                typ = str(m["type"]).strip().lower()
                if typ == "erreur":
                    invalide.loc[idx[i]] = True
                    evts.append((t, dt[i], "erreur (manuel)", np.nan, m.get("commentaire", "")))
                    i += 1
                    continue
                if typ == "division":
                    evts.append((t, dt[i], "division (manuel)", float(m["facteur"]),
                                 m.get("commentaire", "")))
                elif typ == "ignorer":
                    evts.append((t, dt[i], "saut validé (manuel)", np.nan,
                                 m.get("commentaire", "")))
                i_prec, i = i, i + 1
                continue
            if abs(r) <= seuil:
                i_prec, i = i, i + 1
                continue
            # 1) erreur ponctuelle : retour au niveau d'avant dans la fenêtre
            retour = None
            for j in range(i + 1, min(i + 1 + k, len(idx))):
                if abs(px[j] / prec - 1) <= seuil:
                    retour = j
                    break
            if retour is not None:
                invalide.loc[idx[i:retour]] = True
                evts.append((t, dt[i], "erreur ponctuelle", np.nan,
                             f"cours {px[i]:.0f} au lieu d'environ {prec:.0f}, "
                             f"{retour - i} séance(s) écartée(s)"))
                i = retour
                continue
            # 2) division ou regroupement du nominal
            n = _entier_proche(prec / px[i], tol)
            if n:
                evts.append((t, dt[i], "division probable", float(n),
                             f"cours {prec:.0f} -> {px[i]:.0f} (rapport {prec / px[i]:.2f})"))
            else:
                m_ = _entier_proche(px[i] / prec, tol)
                if m_:
                    evts.append((t, dt[i], "regroupement probable", 1 / m_,
                                 f"cours {prec:.0f} -> {px[i]:.0f}"))
                else:
                    evts.append((t, dt[i], "saut inexpliqué", np.nan,
                                 f"variation de {r:+.0%} en une séance ({prec:.0f} -> {px[i]:.0f})"))
            i_prec, i = i, i + 1

    evenements = pd.DataFrame(evts, columns=["ticker", "date", "type", "facteur", "detail"])
    evenements["date"] = pd.to_datetime(evenements["date"])
    return evenements, invalide


# ---------------------------------------------------------------- corrections
def appliquer_corrections(cours: pd.DataFrame, div: pd.DataFrame,
                          evenements: pd.DataFrame, invalide: pd.Series
                          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Écarte les lignes erronées et ajuste l'historique des divisions de nominal."""
    c = cours.loc[~invalide].copy()
    d = div.copy()
    c["facteur_ajust"] = 1.0
    d["facteur_ajust"] = 1.0
    divisions = evenements[evenements["facteur"].notna()]
    for _, e in divisions.iterrows():
        avant_c = (c["ticker"] == e["ticker"]) & (c["date"] < e["date"])
        avant_d = (d["ticker"] == e["ticker"]) & (d["date_detachement"] < e["date"])
        c.loc[avant_c, "facteur_ajust"] *= e["facteur"]
        d.loc[avant_d, "facteur_ajust"] *= e["facteur"]
    for col in ["ouverture", "haut", "bas", "cloture"]:
        c[col] = c[col] / c["facteur_ajust"]
    c["volume_titres"] = c["volume_titres"] * c["facteur_ajust"]
    d["montant_ajuste"] = d["montant"] / d["facteur_ajust"]
    return c.reset_index(drop=True), d


def valider_dividendes(d: pd.DataFrame, fond: pd.DataFrame, c: pd.DataFrame,
                       cfg: dict) -> pd.DataFrame:
    """Contrôle chaque montant de dividende avant de l'utiliser.

    1. Recoupement avec le dividende par exercice publié par Sikafinance :
       écart <= 15 % : confirmé ; archive plus élevée : ramené au montant
       Sikafinance (on retient toujours le plus bas) ; archive plus basse : conservé.
    2. Sans recoupement possible : un rendement supérieur au seuil
       (dividende / cours de la veille) rend le montant non fiable ; il est
       alors exclu des calculs (traité comme inconnu, jamais comme zéro).
    """
    seuil = cfg["qualite"]["dividende_suspect"]
    d = d.copy()
    d["exercice"] = pd.to_numeric(d.get("exercice"), errors="coerce")
    ref = {}
    if fond is not None and len(fond):
        f = fond[fond["indicateur"] == "dividende"].copy()
        f["exercice"] = pd.to_datetime(f["date"]).dt.year
        ref = f.groupby(["ticker", "exercice"])["valeur"].last().to_dict()
    somme = d.groupby(["ticker", "exercice"])["montant"].sum().to_dict()

    px = c.set_index(["ticker", "date"])["cloture"].sort_index()
    retenu, statut = [], []
    for _, r in d.iterrows():
        cle = (r["ticker"], r["exercice"])
        facteur = r.get("facteur_ajust", 1.0)
        if cle in ref and somme.get(cle):
            rapport = somme[cle] / ref[cle]
            if rapport > 1.15:
                retenu.append(r["montant"] * ref[cle] / somme[cle] / facteur)
                statut.append(f"corrigé : ramené au montant Sikafinance ({ref[cle]:.0f})")
            elif rapport < 0.85:
                retenu.append(r["montant_ajuste"])
                statut.append("conservé (inférieur au montant Sikafinance)")
            else:
                retenu.append(r["montant_ajuste"])
                statut.append("confirmé par Sikafinance")
            continue
        try:
            serie = px.loc[r["ticker"]]
            avant = serie[serie.index < r["date_detachement"]]
        except KeyError:
            avant = pd.Series(dtype=float)
        if not len(avant):
            retenu.append(r["montant_ajuste"])
            statut.append("non vérifié (pas de cours antérieur)")
        elif r["montant_ajuste"] / avant.iloc[-1] > seuil:
            retenu.append(np.nan)
            statut.append(f"non fiable : {r['montant_ajuste'] / avant.iloc[-1]:.0%} du cours")
        else:
            retenu.append(r["montant_ajuste"])
            statut.append("plausible (non recoupé)")
    d["montant_retenu"] = retenu
    d["statut"] = statut
    return d


def ajouter_rendement_total(c: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    """Ajoute le dividende du jour, le rendement quotidien total et un indice base 100.

    L'indice de rendement total ne baisse pas au détachement : le dividende
    est réintégré. C'est lui qui sert aux signaux et au backtest.
    """
    c = c.sort_values(["ticker", "date"]).reset_index(drop=True)
    dd = d[["ticker", "date_detachement", "montant_retenu"]].rename(
        columns={"montant_retenu": "montant"})
    c["dividende"] = rattacher_dividendes(c, dd)
    prec = c.groupby("ticker")["cloture"].shift(1)
    c["r_total"] = ((c["cloture"] + c["dividende"]) / prec - 1).fillna(0.0)
    c["indice_rt"] = 100 * (1 + c["r_total"]).groupby(c["ticker"]).cumprod()
    return c


def marquer_suspensions(c: pd.DataFrame, evenements: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Suspend un titre pendant N séances après un saut inexpliqué."""
    n = cfg["qualite"]["suspension_apres_saut"]
    c["suspendu"] = False
    for _, e in evenements[evenements["type"] == "saut inexpliqué"].iterrows():
        lignes = c.index[(c["ticker"] == e["ticker"]) & (c["date"] >= e["date"])][:n]
        c.loc[lignes, "suspendu"] = True
    return c


# ---------------------------------------------------------------- anomalies
def controles(c: pd.DataFrame, d: pd.DataFrame, evenements: pd.DataFrame,
              cfg: dict) -> pd.DataFrame:
    """Liste lisible de tout ce qui mérite l'attention de l'utilisateur."""
    q = cfg["qualite"]
    anomalies = []
    for _, e in evenements.iterrows():
        anomalies.append((e["date"], e["ticker"], e["type"], e["detail"]))

    derniere = c["date"].max()
    for t, g in c.groupby("ticker"):
        if (derniere - g["date"].max()).days > q["fraicheur_max_jours"]:
            anomalies.append((g["date"].max(), t, "titre plus coté",
                              "aucune cotation récente (radié ou suspendu)"))
        recent = g[g["date"] > derniere - pd.Timedelta(days=365)]
        sans = int((recent["volume_titres"].fillna(0) == 0).sum())
        if sans:
            anomalies.append((derniere, t, "séances sans échange",
                              f"{sans} séance(s) sans échange sur 12 mois"))
        manquants = int(recent[["haut", "bas"]].isna().any(axis=1).sum())
        if manquants:
            anomalies.append((derniere, t, "données incomplètes",
                              f"plus haut ou plus bas manquant sur {manquants} séance(s) "
                              f"(sans effet sur les signaux, fondés sur la clôture)"))

    # dividendes corrigés ou écartés
    for _, r in d[~d["statut"].str.startswith(("confirmé", "plausible"))].iterrows():
        anomalies.append((r["date_detachement"], r["ticker"], "dividende à vérifier",
                          f"montant archive {r['montant']:.0f} FCFA : {r['statut']}"))

    if (pd.Timestamp.today().normalize() - derniere).days > q["fraicheur_max_jours"]:
        anomalies.append((derniere, "TOUS", "données périmées",
                          f"dernière séance au {derniere:%d/%m/%Y} : lancez une mise à jour"))

    out = pd.DataFrame(anomalies, columns=["date", "ticker", "type", "detail"])
    return out.sort_values(["type", "ticker", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------- pipeline
def preparer(sources: dict, cfg: dict) -> dict:
    """Chaîne complète du module 1 : détection, corrections, rendement total, contrôles."""
    cours = sources["cours"].sort_values(["ticker", "date"]).reset_index(drop=True)
    div = sources["dividendes"]
    evts, invalide = detecter_evenements(cours, div, cfg, sources.get("evenements_manuels"))
    c, d = appliquer_corrections(cours, div, evts, invalide)
    d = valider_dividendes(d, sources.get("fondamentaux_archive"), c, cfg)
    c = ajouter_rendement_total(c, d)
    c = marquer_suspensions(c, evts, cfg)
    anomalies = controles(c, d, evts, cfg)
    return {"cours": c, "dividendes": d, "evenements": evts, "anomalies": anomalies,
            "referentiel": sources["referentiel"], "indice": sources.get("indice")}
