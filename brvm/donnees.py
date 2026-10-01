"""Module 1 : récupération, import et stockage des données.

Trois sources, par ordre de priorité décroissante :
1. fichiers importés à la main (dossier donnees/manuel) : ils corrigent tout ;
2. archive publique blakro/brvm (licence MIT), mise à jour chaque séance ;
3. API Sikafinance, en secours pour compléter les dernières séances.
"""
from __future__ import annotations

import io
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from .config import RACINE, chemin

FICHIERS_ARCHIVE = ("cours", "dividendes", "referentiel", "fondamentaux")
COLONNES_COURS = ["date", "ticker", "ouverture", "haut", "bas", "cloture",
                  "volume_titres", "volume_fcfa"]

# Dernière lettre du ticker = pays d'origine (convention BRVM)
SUFFIXE_PAYS = {"C": ".ci", "S": ".sn", "B": ".bj", "F": ".bf", "M": ".ml",
                "N": ".ne", "T": ".tg", "G": ".gw"}
URL_SIKA = "https://www.sikafinance.com/api/general/GetHistos"


# ---------------------------------------------------------------- téléchargement
def telecharger_archive(cfg: dict, timeout: int = 60) -> dict:
    """Met à jour les CSV de l'archive. Renvoie un compte rendu par fichier.

    En cas d'échec, l'ancienne version est conservée (jamais écrasée par du vide).
    """
    dossier = chemin(cfg, "dossier_archive")
    dossier.mkdir(parents=True, exist_ok=True)
    rapport = {}
    for nom in FICHIERS_ARCHIVE:
        url = f"{cfg['donnees']['url_archive']}/{nom}.csv"
        try:
            rep = requests.get(url, timeout=timeout)
            rep.raise_for_status()
            df = pd.read_csv(io.StringIO(rep.text))
            if df.empty:
                raise ValueError("fichier vide")
            (dossier / f"{nom}.csv").write_text(rep.text, encoding="utf-8")
            rapport[nom] = f"OK ({len(df)} lignes)"
        except Exception as e:  # noqa: BLE001 - on veut tout rapporter
            rapport[nom] = f"ÉCHEC : {e}. Ancienne version conservée."
    return rapport


def symbole_sika(ticker: str) -> str:
    return ticker + SUFFIXE_PAYS.get(ticker[-1], ".ci")


def telecharger_sikafinance(ticker: str, debut: date, fin: date,
                            timeout: int = 30) -> pd.DataFrame:
    """Historique journalier d'un titre via l'API Sikafinance (fenêtres de 89 jours).

    Le champ Volume de l'API compte des titres ; le montant en FCFA est
    reconstitué avec le prix moyen de séance (milieu du plus haut et du plus bas).
    """
    lignes = []
    d = debut
    while d <= fin:
        f = min(d + timedelta(days=89), fin)
        corps = {"ticker": symbole_sika(ticker), "datedeb": d.isoformat(),
                 "datefin": f.isoformat(), "xperiod": "0"}
        rep = requests.post(URL_SIKA, json=corps, timeout=timeout)
        rep.raise_for_status()
        lignes += rep.json().get("lst") or []
        d = f + timedelta(days=1)
    if not lignes:
        return pd.DataFrame(columns=COLONNES_COURS)
    df = pd.DataFrame(lignes)
    out = pd.DataFrame({
        "date": pd.to_datetime(df["Date"], dayfirst=True),
        "ticker": ticker,
        "ouverture": pd.to_numeric(df.get("Open"), errors="coerce"),
        "haut": pd.to_numeric(df.get("High"), errors="coerce"),
        "bas": pd.to_numeric(df.get("Low"), errors="coerce"),
        "cloture": pd.to_numeric(df.get("Close"), errors="coerce"),
        "volume_titres": pd.to_numeric(df.get("Volume"), errors="coerce"),
    })
    out["volume_fcfa"] = out["volume_titres"] * (out["haut"] + out["bas"]) / 2
    return out[COLONNES_COURS]


def completer_avec_sikafinance(cfg: dict, cours: pd.DataFrame,
                               tickers: list[str]) -> tuple[pd.DataFrame, dict]:
    """Ajoute les séances manquantes depuis la dernière date connue (secours)."""
    rapport, ajouts = {}, []
    derniere = cours["date"].max().date() if len(cours) else date(2015, 1, 1)
    for t in tickers:
        try:
            df = telecharger_sikafinance(t, derniere + timedelta(days=1), date.today())
            ajouts.append(df)
            rapport[t] = f"{len(df)} séance(s) ajoutée(s)"
        except Exception as e:  # noqa: BLE001
            rapport[t] = f"ÉCHEC : {e}"
    if ajouts:
        cours = pd.concat([cours, *ajouts], ignore_index=True)
        cours = cours.drop_duplicates(["date", "ticker"], keep="first")
    return cours, rapport


# ---------------------------------------------------------------- import manuel
SYNONYMES = {
    "date": ["date", "séance", "seance"],
    "ticker": ["ticker", "symbole", "code", "titre"],
    "ouverture": ["ouverture", "open", "cours d'ouverture"],
    "haut": ["haut", "plus haut", "high"],
    "bas": ["bas", "plus bas", "low"],
    "cloture": ["cloture", "clôture", "close", "dernier", "cours de clôture"],
    "volume_titres": ["volume_titres", "volume", "volume titres", "quantité", "quantite"],
    "volume_fcfa": ["volume_fcfa", "valeur", "volume fcfa", "montant", "capitaux"],
}


def _nombre(serie: pd.Series) -> pd.Series:
    """Convertit « 12 345,50 » ou « 12,345.50 » en nombre."""
    if serie.dtype.kind in "if":
        return serie
    s = serie.astype(str).str.replace(" ", "").str.replace(" ", "")
    virgule_decimale = s.str.contains(",").any() and not s.str.contains(r"\.\d{3}").any()
    if virgule_decimale:
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        s = s.str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def normaliser_fichier(df: pd.DataFrame, ticker_defaut: str | None = None) -> pd.DataFrame:
    """Renomme les colonnes d'un export (Sikafinance, Excel perso...) au format interne."""
    correspondance = {}
    for col in df.columns:
        nom = str(col).strip().lower()
        for cible, variantes in SYNONYMES.items():
            if nom in variantes and cible not in correspondance.values():
                correspondance[col] = cible
                break
    df = df.rename(columns=correspondance)
    if "ticker" not in df.columns:
        if not ticker_defaut:
            raise ValueError("Colonne ticker absente : précisez le code du titre.")
        df["ticker"] = ticker_defaut
    if "date" not in df.columns or "cloture" not in df.columns:
        raise ValueError("Il faut au minimum une colonne date et une colonne clôture.")
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    for col in COLONNES_COURS[2:]:
        df[col] = _nombre(df[col]) if col in df.columns else float("nan")
    manque = df["volume_fcfa"].isna() & df["volume_titres"].notna()
    df.loc[manque, "volume_fcfa"] = df.loc[manque, "volume_titres"] * df.loc[manque, "cloture"]
    df["ticker"] = df["ticker"].astype(str).str.upper().str.replace(r"\..*$", "", regex=True)
    return df.dropna(subset=["date", "cloture"])[COLONNES_COURS]


def lire_fichier(source, ticker_defaut: str | None = None) -> pd.DataFrame:
    """Lit un CSV ou un Excel (chemin ou fichier téléversé) et le normalise."""
    nom = getattr(source, "name", str(source)).lower()
    if nom.endswith((".xlsx", ".xls")):
        brut = pd.read_excel(source)
    else:
        brut = pd.read_csv(source, sep=None, engine="python")
    return normaliser_fichier(brut, ticker_defaut)


# ---------------------------------------------------------------- base locale
def _lire_csv(p: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(p, **kw) if p.exists() else pd.DataFrame()


def charger_sources(cfg: dict) -> dict[str, pd.DataFrame]:
    """Assemble archive + fichiers manuels (les fichiers manuels priment)."""
    arch = chemin(cfg, "dossier_archive")
    man = chemin(cfg, "dossier_manuel")

    cours = _lire_csv(arch / "cours.csv", parse_dates=["date"])
    manuels = [lire_fichier(p) for p in sorted(man.glob("cours_*.*"))]
    if manuels:
        cours = pd.concat([*manuels, cours], ignore_index=True)
    cours = (cours.drop_duplicates(["date", "ticker"], keep="first")
                  .sort_values(["ticker", "date"]).reset_index(drop=True))

    div = _lire_csv(arch / "dividendes.csv", parse_dates=["date_detachement"])
    div_man = _lire_csv(man / "dividendes_manuels.csv", parse_dates=["date_detachement"])
    if len(div_man):
        div = pd.concat([div_man, div], ignore_index=True)
    div = div.drop_duplicates(["ticker", "date_detachement"], keep="first")

    ref = _lire_csv(arch / "referentiel.csv")
    ref = ref[ref["ticker"] != "ticker"] if len(ref) else ref

    indice = pd.DataFrame(columns=["date", "valeur"])
    fichiers_indice = sorted(man.glob("indice_*.*"))
    if fichiers_indice:
        brut = lire_fichier(fichiers_indice[-1], ticker_defaut="BRVMC")
        indice = brut[["date", "cloture"]].rename(columns={"cloture": "valeur"})
        indice = indice.sort_values("date").drop_duplicates("date")

    evts = _lire_csv(man / "evenements_manuels.csv", parse_dates=["date"])
    fond = _lire_csv(arch / "fondamentaux.csv", parse_dates=["date"])
    return {"cours": cours, "dividendes": div, "referentiel": ref,
            "indice": indice, "evenements_manuels": evts,
            "fondamentaux_archive": fond}


def enregistrer_sqlite(cfg: dict, tables: dict[str, pd.DataFrame]) -> Path:
    """Écrit toutes les tables dans la base SQLite locale (remplacement complet)."""
    base = chemin(cfg, "base_sqlite")
    base.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(base) as cx:
        for nom, df in tables.items():
            if isinstance(df, pd.DataFrame):
                df.to_sql(nom, cx, if_exists="replace", index=False)
    return base


def lire_sqlite(cfg: dict, table: str) -> pd.DataFrame:
    base = chemin(cfg, "base_sqlite")
    with sqlite3.connect(base) as cx:
        return pd.read_sql(f"SELECT * FROM {table}", cx)


def mettre_a_jour(cfg: dict, avec_sikafinance: bool = True) -> dict:
    """Bouton « Mettre à jour » : archive, puis Sikafinance pour les séances manquantes."""
    rapport = {"archive": telecharger_archive(cfg)}
    if avec_sikafinance:
        src = charger_sources(cfg)
        actifs = src["referentiel"]
        derniere_vue = pd.to_datetime(actifs["derniere_vue"])
        tickers = actifs.loc[derniere_vue >= derniere_vue.max() - pd.Timedelta(days=30),
                             "ticker"].tolist()
        if (date.today() - src["cours"]["date"].max().date()).days > 1:
            cours, rap = completer_avec_sikafinance(cfg, src["cours"], tickers)
            nouvelles = cours[cours["date"] > src["cours"]["date"].max()]
            if len(nouvelles):
                man = chemin(cfg, "dossier_manuel")
                man.mkdir(parents=True, exist_ok=True)
                nouvelles.to_csv(man / f"cours_sikafinance_{date.today():%Y%m%d}.csv",
                                 index=False)
            rapport["sikafinance"] = rap
    return rapport


def modele_fondamentaux(chemin_sortie: Path | None = None) -> Path:
    """Crée le fichier Excel de saisie des états financiers (s'il n'existe pas)."""
    p = chemin_sortie or RACINE / "donnees_perso" / "fondamentaux_saisis.xlsx"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=[
            "ticker", "exercice", "chiffre_affaires", "benefice_net",
            "capitaux_propres", "dettes_financieres",
            "tresorerie_et_placements_a_interet", "revenus_non_conformes",
            "nombre_titres", "source", "date_saisie",
        ]).to_excel(p, index=False)
    return p
