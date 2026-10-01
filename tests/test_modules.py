"""Tests des règles clés, sur données synthétiques contrôlées (python -m pytest)."""
import numpy as np
import pandas as pd
import pytest

from brvm import backtest as bt
from brvm import fondamental, liquidite, qualite, signaux
from brvm.config import charger_config
from brvm.filtres import appliquer_filtres
from brvm.risque import commission_sgi, dimensionner, frais_ordre


@pytest.fixture
def cfg():
    return charger_config()


def cours_synthetiques(prix: dict, debut="2020-01-01", volume=1000.0) -> pd.DataFrame:
    lignes = []
    for t, serie in prix.items():
        dates = pd.bdate_range(debut, periods=len(serie))
        for d, p in zip(dates, serie):
            lignes.append((d, t, p, p, p, p, volume, volume * p))
    return pd.DataFrame(lignes, columns=["date", "ticker", "ouverture", "haut", "bas",
                                         "cloture", "volume_titres", "volume_fcfa"])


VIDE_DIV = pd.DataFrame(columns=["ticker", "date_detachement", "montant", "exercice"])


# ---------------------------------------------------------------- frais
def test_commission_tranches_cumulatives(cfg):
    assert commission_sgi(1_000_000, cfg) == pytest.approx(8_000)
    # 500 M à 0,80 % + 100 M à 0,60 %
    assert commission_sgi(600_000_000, cfg) == pytest.approx(4_000_000 + 600_000)


def test_frais_ordre_inclut_marche_et_taxes(cfg):
    f = cfg["frais"]
    attendu = 1_000_000 * (0.008 + f["commission_brvm"] + f["commission_dcbr"]
                           + f["frais_complementaires_estimes"])
    assert frais_ordre(1_000_000, cfg) == pytest.approx(attendu)


# ---------------------------------------------------------------- qualité
def test_erreur_ponctuelle_ecartee(cfg):
    c = cours_synthetiques({"AAA": [1000, 1000, 500, 1000, 1010, 1020]})
    evts, inval = qualite.detecter_evenements(c, VIDE_DIV, cfg)
    assert list(evts["type"]) == ["erreur ponctuelle"]
    assert inval.sum() == 1 and c.loc[inval, "cloture"].iloc[0] == 500


def test_division_detectee_et_historique_ajuste(cfg):
    c = cours_synthetiques({"AAA": [1000] * 5 + [500] * 10})
    evts, inval = qualite.detecter_evenements(c, VIDE_DIV, cfg)
    assert evts.iloc[0]["type"] == "division probable" and evts.iloc[0]["facteur"] == 2
    c2, _ = qualite.appliquer_corrections(c, VIDE_DIV.assign(montant=[]), evts, inval)
    assert c2["cloture"].nunique() == 1  # tout l'historique ramené à 500


def test_saut_inexplique_suspend_le_titre(cfg):
    c = cours_synthetiques({"AAA": [1000] * 5 + [700] * 10})
    evts, _ = qualite.detecter_evenements(c, VIDE_DIV, cfg)
    assert evts.iloc[0]["type"] == "saut inexpliqué"
    c = qualite.marquer_suspensions(c, evts, cfg)
    assert c["suspendu"].iloc[5:].all() and not c["suspendu"].iloc[:5].any()


def test_evenement_manuel_prioritaire(cfg):
    c = cours_synthetiques({"AAA": [1000] * 5 + [700] * 10})
    manuel = pd.DataFrame({"ticker": ["AAA"], "date": [c["date"].iloc[5]], "type": ["ignorer"],
                           "facteur": [np.nan], "commentaire": ["augmentation de capital"]})
    evts, _ = qualite.detecter_evenements(c, VIDE_DIV, cfg, manuel)
    assert evts.iloc[0]["type"] == "saut validé (manuel)"


def test_detachement_ne_fait_pas_baisser_le_rendement_total(cfg):
    c = cours_synthetiques({"AAA": [1000, 1000, 950, 950]})
    d = pd.DataFrame({"ticker": ["AAA"], "date_detachement": [c["date"].iloc[2]],
                      "montant": [50.0], "exercice": [2019], "facteur_ajust": [1.0],
                      "montant_ajuste": [50.0], "montant_retenu": [50.0]})
    out = qualite.ajouter_rendement_total(c, d)
    assert out["indice_rt"].iloc[-1] == pytest.approx(100.0)


def test_dividende_aberrant_juge_non_fiable(cfg):
    c = cours_synthetiques({"AAA": [1000] * 5})
    d = pd.DataFrame({"ticker": ["AAA"], "date_detachement": [c["date"].iloc[3]],
                      "montant": [900.0], "exercice": [2019], "facteur_ajust": [1.0],
                      "montant_ajuste": [900.0]})
    v = qualite.valider_dividendes(d, None, c, cfg)
    assert np.isnan(v["montant_retenu"].iloc[0]) and v["statut"].iloc[0].startswith("non fiable")


def test_dividende_ramene_au_montant_sikafinance(cfg):
    c = cours_synthetiques({"AAA": [1000] * 5})
    d = pd.DataFrame({"ticker": ["AAA"], "date_detachement": [c["date"].iloc[3]],
                      "montant": [100.0], "exercice": [2019], "facteur_ajust": [1.0],
                      "montant_ajuste": [100.0]})
    fond = pd.DataFrame({"ticker": ["AAA"], "date": [pd.Timestamp("2019-12-31")],
                         "indicateur": ["dividende"], "valeur": [50.0]})
    v = qualite.valider_dividendes(d, fond, c, cfg)
    assert v["montant_retenu"].iloc[0] == pytest.approx(50.0)


# ---------------------------------------------------------------- liquidité
def test_filtre_liquidite(cfg):
    c = cours_synthetiques({"LIQ": [1000] * 80, "ILLIQ": [1000] * 80})
    c.loc[c["ticker"] == "ILLIQ", ["volume_titres", "volume_fcfa"]] = [1, 1000]
    c["indice_rt"], c["suspendu"] = 100.0, False
    mat = liquidite.construire_matrices(c)
    el = liquidite.liquidite(mat, cfg)["eligible"].iloc[-1]
    assert el["LIQ"] and not el["ILLIQ"]


# ---------------------------------------------------------------- score et filtres
def test_rendement_inconnu_si_dividende_non_fiable():
    d = pd.DataFrame({"ticker": ["A", "B"], "date_detachement": pd.to_datetime(["2024-06-01"] * 2),
                      "montant_retenu": [np.nan, 50.0], "exercice": [2023, 2023]})
    r = fondamental.rendement_12m(d, pd.Series({"A": 1000.0, "B": 1000.0}),
                                  pd.Timestamp("2024-12-31"))
    assert np.isnan(r["A"]) and r["B"] == pytest.approx(0.05)


def test_score_sans_donnee_obligatoire_est_vide(cfg):
    crit = pd.DataFrame({"rendement": [0.08, np.nan, 0.05], "regularite": [1.0, 1.0, 0.6]},
                        index=["A", "B", "C"])
    s = fondamental.score_composite(crit, cfg)
    assert np.isnan(s.loc["B", "score"]) and s.loc["A", "score"] > s.loc["C", "score"]


def test_exclusion_deontologique_et_conformite(cfg):
    cfg = {**cfg, "filtres": {**cfg["filtres"], "conformite_islamique": True}}
    excl = pd.DataFrame({"ticker": ["A"], "motif": ["client audité"]})
    act = pd.DataFrame({"ticker": ["B"], "statut": ["non conforme"], "motif": ["alcool"]})
    f = appliquer_filtres(["A", "B", "C"], pd.Series({"A": 1, "B": 1, "C": 1}), cfg, excl, act,
                          None)
    assert not f.loc["A", "admis"] and not f.loc["B", "admis"] and f.loc["C", "admis"]
    assert f.loc["C", "conformite"].startswith("activité admissible a priori")


def test_mode_strict_exige_les_ratios(cfg):
    cfg = {**cfg, "filtres": {**cfg["filtres"], "conformite_islamique": True,
                              "mode_conformite": "strict"}}
    vide = pd.DataFrame(columns=["ticker", "statut", "motif"])
    f = appliquer_filtres(["C"], pd.Series({"C": 1}), cfg, pd.DataFrame(columns=["ticker"]),
                          vide, None)
    assert not f.loc["C", "admis"]  # jamais conforme par défaut


# ---------------------------------------------------------------- signaux et risque
def test_stop_suiveur_declenche_vente(cfg):
    idx = pd.bdate_range("2024-01-01", periods=5)
    rt = pd.Series([100, 120, 130, 105, 100], index=idx, dtype=float)
    pos = pd.Series({"date_achat": idx[0]})
    action, raisons = signaux.regles_sortie(pos, rt, idx[-1], pd.Series({"retournement": False}),
                                            70, cfg)
    assert action == "VENDRE" and "stop" in raisons[0]


def test_dimensionnement_respecte_plafond_sectoriel(cfg):
    cand = pd.DataFrame({"score": [90, 80, 70, 60], "cours": [1000.0] * 4,
                         "montant_median_fcfa": [1e9] * 4}, index=["A", "B", "C", "D"])
    secteurs = pd.Series({"A": "Banque", "B": "Banque", "C": "Banque", "D": "Banque"})
    t = dimensionner(cand, cfg, {}, secteurs)
    assert t["montant_fcfa"].sum() <= cfg["risque"]["capital_fcfa"] * cfg["risque"][
        "poids_max_secteur"] + 1


# ---------------------------------------------------------------- backtest
def test_backtest_execute_le_lendemain_et_paie_les_frais(cfg):
    c = cours_synthetiques({"AAA": list(np.linspace(1000, 1500, 400))}, debut="2019-01-01",
                           volume=100_000)
    c["indice_rt"] = 100 * c["cloture"] / 1000
    c["suspendu"], c["dividende"] = False, 0.0
    mat = liquidite.construire_matrices(c)
    prep = {"matrices": mat, "liquidite": liquidite.liquidite(mat, cfg), "cours": c,
            "dividendes": pd.DataFrame(columns=["ticker", "date_detachement", "montant_retenu",
                                                "exercice"]),
            "indicateurs": signaux.indicateurs(mat["rt"], cfg)}
    cfg = {**cfg, "backtest": {**cfg["backtest"], "debut": "2019-06-01"}}
    ctx = bt.contexte(prep, cfg)
    ctx["scores"] = {d: pd.Series({"AAA": 90.0}) for d in ctx["revisions"]}
    res = bt.simuler(ctx, cfg, bt.Parametres(utiliser_tendance=False))
    achat = res.operations[res.operations["sens"] == "achat"].iloc[0]
    assert achat["date"] > ctx["revisions"][0]      # jamais au cours de décision
    assert achat["frais"] > 0 and res.frais_totaux > 0
