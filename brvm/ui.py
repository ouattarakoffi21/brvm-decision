"""Éléments communs à toutes les pages de l'application Streamlit."""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import streamlit as st

from .config import charger_config, chemin
from .moteur import decisions_du_jour, preparer_tout

AVERTISSEMENT = ("Outil d'aide à la décision, pas un conseil en investissement. "
                 "Les performances passées ne préjugent pas des performances futures. "
                 "Tu restes seul décideur de tes ordres et responsable des risques de perte.")

COULEURS_ACTION = {"VENDRE": "🔴", "ALLÉGER": "🟠", "ACHAT": "🟢", "CONSERVER": "🔵",
                   "SURVEILLER": "🟡", "NEUTRE": "⚪", "ÉCARTÉ": "⚫"}


def page(titre: str) -> dict:
    """En-tête commun : configuration, verrou, avertissement. Renvoie la config active."""
    verrou()
    if "cfg" not in st.session_state:
        st.session_state["cfg"] = charger_config()
    st.title(titre)
    st.caption("⚠️ " + AVERTISSEMENT)
    return st.session_state["cfg"]


def verrou() -> None:
    """Mot de passe facultatif (secrets Streamlit), indispensable en ligne."""
    try:
        attendu = st.secrets.get("mot_de_passe")
    except Exception:  # noqa: BLE001 - pas de fichier secrets en local
        attendu = None
    if not attendu or st.session_state.get("ouvert"):
        return
    saisi = st.text_input("Mot de passe", type="password")
    if saisi and saisi == attendu:
        st.session_state["ouvert"] = True
        st.rerun()
    if saisi:
        st.error("Mot de passe incorrect.")
    st.stop()


def _empreinte(cfg: dict) -> str:
    """Change quand la config ou les fichiers de données changent (invalide le cache)."""
    fichiers = sorted(p.stat().st_mtime for dossier in ("dossier_archive", "dossier_manuel")
                      for p in chemin(cfg, dossier).glob("*.*"))
    return hashlib.md5((json.dumps(cfg, sort_keys=True, default=str)
                        + str(fichiers)).encode()).hexdigest()


@st.cache_data(show_spinner="Préparation des données (contrôle qualité, indicateurs)...")
def _preparer(empreinte: str, cfg_json: str) -> dict:
    return preparer_tout(json.loads(cfg_json))


def donnees(cfg: dict) -> dict:
    return _preparer(_empreinte(cfg), json.dumps(cfg, default=str))


def decisions(cfg: dict) -> dict:
    return decisions_du_jour(donnees(cfg), cfg)


def carte_signal(t: str, r) -> None:
    """Carte lisible sur téléphone : signal, chiffres clés et justification complète."""
    with st.container(border=True):
        st.markdown(f"{COULEURS_ACTION[r['action']]} **{r['action']} · {t}** · {r['societe']}")
        score = "n.d." if pd.isna(r["score"]) else f"{r['score']:.0f}"
        cours = f"{r['cours']:,.0f}".replace(",", " ")
        st.caption(f"Cours **{cours}** · Score **{score}** · Rendement 12 m "
                   f"**{pct(r['rendement_12m'])}** · Momentum 6 m "
                   f"**{pct(r['momentum_6m'], True)}**")
        for raison in str(r["justification"]).split(" ; "):
            st.markdown(f"- {raison}")


def fcfa(x) -> str:
    return "" if pd.isna(x) else f"{x:,.0f} FCFA".replace(",", " ")


def pct(x, signe: bool = False) -> str:
    """Pourcentage au format français : 12,3 %."""
    if pd.isna(x):
        return "n.d."
    txt = f"{x * 100:+.1f}" if signe else f"{x * 100:.1f}"
    return txt.replace(".", ",") + " %"


def points(x) -> str:
    """Écart entre deux pourcentages, en points : +2,5 pts."""
    return "n.d." if pd.isna(x) else f"{x * 100:+.1f} pts".replace(".", ",")


def bandeau_donnees(prep: dict) -> None:
    derniere = prep["cours"]["date"].max()
    age = (pd.Timestamp.today().normalize() - derniere).days
    msg = f"Données au **{derniere:%d/%m/%Y}** (dernière séance archivée)."
    (st.info if age <= 4 else st.error)(
        msg + ("" if age <= 4 else " Données périmées : mets-les à jour dans « Paramètres »."))
