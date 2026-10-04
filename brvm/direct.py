"""Module 10 : séance en direct.

Lit la page des cotations de Sikafinance pendant la séance, ajoute le cours
du moment comme une séance provisoire, puis réapplique exactement les mêmes
règles que les signaux officiels (score, tendance, stop suiveur). Ce module
ne prévoit rien : il dit ce que deviendraient les signaux si la séance
fermait au cours affiché.
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

from . import signaux

URL_COTATIONS = "https://www.sikafinance.com/marches/aaz"
# Séance BRVM, heure d'Abidjan (UTC+0). Bornes larges : pré-ouverture et clôture.
OUVERTURE_H, CLOTURE_H = 9, 15
SAUT_SUSPECT = 0.12  # au-delà du plafond de variation (~7,5 %), le cours lu est ignoré


def _nombre(texte) -> float:
    if texte is None or (isinstance(texte, float) and np.isnan(texte)):
        return np.nan
    t = re.sub(r"[\s  %]", "", str(texte)).replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return np.nan


def _norme(nom: str) -> str:
    n = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", n)


def analyser_page(html_page: str, referentiel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Extrait le tableau des actions (nom, ouverture, haut, bas, volumes, dernier, variation)."""
    tables = pd.read_html(io.StringIO(html_page), extract_links="body")
    cible = None
    for t in tables:
        cols = [str(c).lower() for c in t.columns]
        if any("dernier" in c for c in cols) and any("xof" in c or "fcfa" in c for c in cols):
            cible = t
            break
    if cible is None:
        raise ValueError("tableau des cotations introuvable sur la page")
    cols = {str(c).lower(): c for c in cible.columns}

    def col(*mots):
        for k, c in cols.items():
            if all(m in k for m in mots):
                return c
        return None

    c_nom, c_dern, c_var = col("nom"), col("dernier"), col("variation")
    c_ouv, c_haut, c_bas = col("ouverture"), col("haut"), col("bas")
    c_vt, c_vx = col("volume", "titres"), col("volume", "xof")
    noms_ref = {}
    if referentiel is not None and len(referentiel):
        noms_ref = {_norme(n): t for t, n in zip(referentiel["ticker"], referentiel["nom"])}
    lignes = []
    for _, r in cible.iterrows():
        nom, lien = r[c_nom] if isinstance(r[c_nom], tuple) else (r[c_nom], None)
        m = re.search(r"cotation_([A-Z0-9]+)\.", lien or "")
        ticker = m.group(1) if m else None
        if ticker is None and noms_ref:  # repli : rapprochement par le nom
            n = _norme(nom)
            ticker = next((t for k, t in noms_ref.items() if k.startswith(n) or n.startswith(k)), None)
        if ticker is None:
            continue
        val = lambda c: _nombre(r[c][0] if isinstance(r[c], tuple) else r[c]) if c is not None else np.nan
        lignes.append({"ticker": ticker, "nom": nom, "ouverture": val(c_ouv), "haut": val(c_haut),
                       "bas": val(c_bas), "volume_titres": val(c_vt), "volume_fcfa": val(c_vx),
                       "dernier": val(c_dern), "variation_source": val(c_var) / 100})
    df = pd.DataFrame(lignes).drop_duplicates("ticker")
    if df.empty or df["dernier"].notna().sum() < 5:
        raise ValueError("cours illisibles sur la page des cotations")
    return df


def lire_cotations(referentiel: pd.DataFrame | None = None, timeout: int = 20) -> pd.DataFrame:
    fichier = os.environ.get("BRVM_COTATIONS_FICHIER")  # tests hors ligne
    if fichier:
        texte = open(fichier, encoding="utf-8").read()
    else:
        r = requests.get(URL_COTATIONS, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (aide-decision-brvm)"})
        r.raise_for_status()
        texte = r.text
    df = analyser_page(texte, referentiel)
    df["lu_a"] = datetime.now(timezone.utc)
    return df


def etat_marche(maintenant: datetime | None = None) -> tuple[bool, pd.Timestamp]:
    """(séance en cours ?, date de la séance à laquelle se rapportent les cours affichés)."""
    t = maintenant or datetime.now(timezone.utc)
    jour = t.date()
    if t.weekday() < 5 and t.hour >= OUVERTURE_H:
        return t.hour < CLOTURE_H, pd.Timestamp(jour)
    d = jour - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return False, pd.Timestamp(d)


def prep_avec_seance(prep: dict, cot: pd.DataFrame, date_seance: pd.Timestamp,
                     cfg: dict) -> tuple[dict | None, pd.DataFrame]:
    """Copie de prep avec la séance provisoire ajoutée (ou mise à jour).

    Renvoie (prep provisoire ou None si la séance est déjà dans l'historique
    définitif, tableau des cours lus enrichi de la variation et des contrôles).
    """
    mat = prep["matrices"]
    clo = mat["cloture"]
    derniere = clo.index[-1]
    base = derniere if date_seance > derniere else clo.index[-2] if date_seance == derniere else None
    veille = clo.loc[base] if base is not None else clo.iloc[-1]
    c = cot.set_index("ticker").copy()
    c["cloture_veille"] = veille.reindex(c.index)
    c["variation"] = c["dernier"] / c["cloture_veille"] - 1
    c["suspect"] = c["variation"].abs() > SAUT_SUSPECT
    med = mat["volume_fcfa"].tail(cfg["liquidite"]["fenetre_seances"]).median()
    c["volume_vs_mediane"] = c["volume_fcfa"] / med.reindex(c.index).replace(0, np.nan)
    if base is None:
        return None, c

    px = c.loc[~c["suspect"], "dernier"].reindex(clo.columns)
    ok = px.notna() & (px > 0)
    nouvelle_clo = veille.where(~ok, px)
    nouveau_rt = mat["rt"].loc[base] * (nouvelle_clo / veille)
    vol = c["volume_fcfa"].reindex(clo.columns).fillna(0.0).where(mat["cote"].loc[base])

    def ajoute(df: pd.DataFrame, ligne: pd.Series) -> pd.DataFrame:
        df = df.loc[:base].copy()
        df.loc[date_seance] = ligne
        return df

    m2 = {
        "cloture": ajoute(clo, nouvelle_clo),
        "rt": ajoute(mat["rt"], nouveau_rt),
        "volume_fcfa": ajoute(mat["volume_fcfa"], vol),
        "suspendu": ajoute(mat["suspendu"], mat["suspendu"].loc[base]),
        "cote": ajoute(mat["cote"], mat["cote"].loc[base]),
    }
    idx = m2["cloture"].index
    liq = {k: v.reindex(idx).ffill() for k, v in prep["liquidite"].items()}
    cours = prep["cours"][prep["cours"]["date"] <= base]
    nouveaux = pd.DataFrame({"date": date_seance, "ticker": px[ok].index,
                             "cloture": px[ok].values})
    p2 = {**prep, "matrices": m2, "liquidite": liq,
          "indicateurs": signaux.indicateurs(m2["rt"], cfg),
          "cours": pd.concat([cours, nouveaux], ignore_index=True)}
    return p2, c


def alertes(officiel: pd.DataFrame, provisoire: pd.DataFrame, cot: pd.DataFrame,
            zones: pd.DataFrame | None, cfg: dict) -> pd.DataFrame:
    """Liste des alertes de séance, de la plus urgente à la moins urgente."""
    lim = 0.07
    lignes = []
    for t, r in provisoire.iterrows():
        avant = officiel["action"].get(t)
        c = cot.loc[t] if t in cot.index else None
        var = c["variation"] if c is not None else np.nan
        detenu = bool(r["detenu"])
        if c is not None and c["suspect"]:
            lignes.append((5, t, "info", "cours lu suspect",
                           f"variation de {var:+.1%} au-delà du plafond de séance : cours ignoré, "
                           "vérifie sur ta plateforme"))
            continue
        if detenu and r["action"] == "VENDRE" and avant != "VENDRE":
            lignes.append((0, t, "sell", "vente déclenchée en séance", r["justification"]))
        elif r["action"] != avant and avant is not None and r["action"] in ("ACHAT", "VENDRE", "ALLÉGER", "SURVEILLER"):
            ton = {"ACHAT": "buy", "VENDRE": "sell", "ALLÉGER": "watch", "SURVEILLER": "watch"}[r["action"]]
            lignes.append((1 if detenu else 2, t, ton, f"{avant} → {r['action']}",
                           f"si la séance fermait à ce cours : {r['justification']}"))
        if r["action"] == "ACHAT" and zones is not None and t in zones.index and c is not None:
            bas, haut = zones.at[t, "entree_bas"], zones.at[t, "entree_haut"]
            if pd.notna(bas) and bas <= c["dernier"] <= haut:
                lignes.append((2, t, "buy", "dans la zone d'entrée",
                               f"cours {c['dernier']:,.0f} entre {bas:,.0f} et {haut:,.0f} FCFA : "
                               "ordre limité possible".replace(",", " ")))
            elif pd.notna(bas) and c["dernier"] < bas:
                lignes.append((3, t, "watch", "sous la zone d'entrée",
                               f"cours {c['dernier']:,.0f} sous {bas:,.0f} FCFA : baisse plus forte "
                               "que d'habitude, vérifie s'il y a une nouvelle".replace(",", " ")))
        if c is not None and (detenu or r["action"] in ("ACHAT", "SURVEILLER")):
            if pd.notna(var) and abs(var) >= lim:
                lignes.append((3, t, "watch", "proche du plafond de variation",
                               f"{var:+.1%} sur la séance : le cours ne peut guère aller plus loin "
                               "aujourd'hui, un ordre au marché risque d'être mal exécuté"))
            if pd.notna(c["volume_vs_mediane"]) and c["volume_vs_mediane"] >= 3:
                lignes.append((4, t, "indigo", "volume inhabituel",
                               f"{c['volume_vs_mediane']:.0f} fois le montant échangé habituel"))
    df = pd.DataFrame(lignes, columns=["priorite", "ticker", "ton", "titre", "detail"])
    return df.sort_values(["priorite", "ticker"]).reset_index(drop=True)
