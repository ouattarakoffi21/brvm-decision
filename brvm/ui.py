"""Éléments communs à toutes les pages de l'application Streamlit."""
from __future__ import annotations

import hashlib
import html
import json

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from .config import _valeur_toml, charger_config, chemin, fusionner
from .donnees import DOSSIER_COMPLEMENT
from .moteur import decisions_du_jour, preparer_tout

AVERTISSEMENT = ("Outil d'aide à la décision, pas un conseil en investissement. "
                 "Les performances passées ne préjugent pas des performances futures. "
                 "Tu restes seul décideur de tes ordres et responsable des risques de perte.")

# Palette de la charte (reprise de l'aperçu) : un ton par signal.
TONS_ACTION = {"VENDRE": "sell", "ALLÉGER": "watch", "ACHAT": "buy", "CONSERVER": "hold",
               "SURVEILLER": "watch", "NEUTRE": "neutral", "ÉCARTÉ": "out"}

CSS = """
<style>
:root{
  --bg:#EEF1F6; --surface:#FFFFFF; --sunk:#F6F8FB; --ink:#141B2D; --muted:#5B6579; --line:#DCE1EA;
  --indigo:#2B3A8C; --indigo-soft:#E4E8F7; --ochre:#B97A12; --ochre-soft:#F6EBD5;
  --buy:#1C8048; --buy-soft:#E1F2E8; --sell:#BE3B26; --sell-soft:#F8E4E0; --hold:#2C64C2; --hold-soft:#E2EBF9;
  --watch:#A26A0B; --watch-soft:#F7EDD6; --neutral:#7D879A; --neutral-soft:#ECEEF2; --out:#4A5366; --out-soft:#E3E6EC;
  --f-display:"Big Shoulders Display","Arial Narrow","Roboto Condensed",sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --ease:cubic-bezier(.2,.7,.2,1);
}
@import url('https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;800&display=swap');

/* entrée douce de chaque page */
[data-testid="stMainBlockContainer"]{padding-top:2.2rem;max-width:1180px;animation:entree .45s var(--ease) both}
@keyframes entree{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes monte{from{opacity:0;transform:translateY(14px) scale(.98)}to{opacity:1;transform:none}}
@keyframes defile{to{transform:translateX(-50%)}}
@keyframes pouls{50%{opacity:.35}}
@keyframes jauge{from{width:0}}

h1,h2,h3{font-family:var(--f-display)!important;letter-spacing:.01em}
h2{font-weight:800!important}
[data-testid="stSidebar"]{border-right:1px solid var(--line)}
[data-testid="stSidebarNavSeparator"]{display:none}

/* en-tête de page */
.hero{margin:0 0 18px}
.hero .eyebrow{font:600 11px/1 var(--f-mono);letter-spacing:.14em;text-transform:uppercase;color:var(--indigo);
  display:flex;align-items:center;gap:8px}
.hero .eyebrow .dot{width:7px;height:7px;border-radius:50%;background:var(--buy);animation:pouls 2.4s ease-in-out infinite}
.hero h1{font:800 clamp(34px,5.4vw,54px)/1 var(--f-display)!important;margin:8px 0 6px!important;padding:0!important;color:var(--ink)}
.hero p{margin:0;color:var(--muted);max-width:68ch}
.avert{font-size:12.5px;color:var(--muted);background:var(--ochre-soft);border-radius:8px;padding:8px 12px;margin:0 0 18px;
  display:flex;gap:8px;align-items:flex-start}
.avert b{color:var(--ochre)}

/* bandeau défilant des cours */
.tape{background:var(--ink);border-radius:10px;overflow:hidden;height:36px;display:flex;align-items:center;margin:0 0 18px;
  mask-image:linear-gradient(90deg,transparent,#000 4%,#000 96%,transparent)}
.tape-track{display:flex;gap:30px;white-space:nowrap;padding-inline:16px;animation:defile 80s linear infinite;will-change:transform}
.tape:hover .tape-track{animation-play-state:paused}
.tk{font:500 12.5px/1 var(--f-mono);display:inline-flex;gap:8px;align-items:baseline;color:#E7EBF4}
.tk b{font-weight:600;letter-spacing:.04em}
.tk .up{color:#57D08E}.tk .dn{color:#FF8C77}.tk .eq{opacity:.55}

.fraicheur{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font:500 12.5px/1.4 var(--f-mono);color:var(--muted);margin:-6px 0 16px}
.fraicheur b{color:var(--ink)} .fraicheur .sep{opacity:.5}
.fraicheur .dot{width:7px;height:7px;border-radius:50%;background:var(--buy);animation:pouls 2.4s ease-in-out infinite}

/* tuiles de chiffres clés */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:4px 0 18px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 16px 14px;display:grid;gap:4px;
  animation:monte .55s var(--ease) both;position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:var(--c,var(--indigo))}
.kpi .v{font:800 40px/1 var(--f-display);color:var(--c,var(--ink));font-variant-numeric:tabular-nums}
.kpi .l{font-size:13px;color:var(--muted)}
.kpi .d{font:500 12px/1.3 var(--f-mono);color:var(--muted)}

/* cartes de signal */
.carte{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:12px;
  padding:14px 16px;margin:0 0 10px;animation:monte .5s var(--ease) both;transition:transform .2s var(--ease),box-shadow .2s}
.carte:hover{transform:translateY(-2px);box-shadow:0 8px 24px -14px rgba(20,27,45,.35)}
.carte .tete{display:flex;flex-wrap:wrap;gap:8px 10px;align-items:center}
.chip{font:600 11px/1 var(--f-mono);letter-spacing:.06em;padding:5px 8px;border-radius:20px;background:var(--cs);color:var(--c)}
.carte .tick{font:800 22px/1 var(--f-display);letter-spacing:.03em}
.carte .nom{color:var(--muted);font-size:13.5px}
.carte .chiffres{display:flex;flex-wrap:wrap;gap:6px 18px;margin:10px 0 6px;font:500 12.5px/1.2 var(--f-mono);color:var(--muted)}
.carte .chiffres b{color:var(--ink);font-weight:600}
.carte ul{margin:6px 0 0;padding-left:18px;font-size:14px}
.carte li{margin:2px 0}
.jauge{height:6px;border-radius:6px;background:var(--neutral-soft);overflow:hidden;width:90px;display:inline-block;vertical-align:middle;margin-left:6px}
.jauge i{display:block;height:100%;background:var(--c);border-radius:6px;animation:jauge .9s var(--ease) both}

.buy{--c:var(--buy);--cs:var(--buy-soft)} .sell{--c:var(--sell);--cs:var(--sell-soft)}
.hold{--c:var(--hold);--cs:var(--hold-soft)} .watch{--c:var(--watch);--cs:var(--watch-soft)}
.neutral{--c:var(--neutral);--cs:var(--neutral-soft)} .out{--c:var(--out);--cs:var(--out-soft)}
.indigo{--c:var(--indigo);--cs:var(--indigo-soft)} .ochre{--c:var(--ochre);--cs:var(--ochre-soft)}

/* composants Streamlit harmonisés */
[data-testid="stMetric"]{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
  animation:monte .55s var(--ease) both}
[data-testid="stMetricValue"]{font-family:var(--f-display);font-weight:800}
.stTabs [data-baseweb="tab-list"]{gap:4px;flex-wrap:wrap}
.stTabs [data-baseweb="tab"]{border-radius:8px 8px 0 0;padding:8px 12px}
[data-testid="stExpander"] details{border-radius:12px;background:var(--surface)}
[data-testid="stPageLink"] a{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;
  transition:transform .2s var(--ease),border-color .2s}
[data-testid="stPageLink"] a:hover{transform:translateY(-2px);border-color:var(--indigo)}
@media (max-width:640px){.kpi .v{font-size:32px}.hero h1{font-size:34px!important}
  [data-testid="stMainBlockContainer"]{padding-left:16px;padding-right:16px}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
"""

# Gabarit des graphiques : mêmes couleurs et polices que l'interface.
pio.templates["brvm"] = go.layout.Template(layout=go.Layout(
    font=dict(family="IBM Plex Sans, system-ui, sans-serif", color="#141B2D", size=13),
    colorway=["#2B3A8C", "#B97A12", "#1C8048", "#9AA3B5", "#BE3B26", "#2C64C2"],
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#E6EAF1", zeroline=False, linecolor="#DCE1EA"),
    yaxis=dict(gridcolor="#E6EAF1", zeroline=False, linecolor="#DCE1EA"),
    hoverlabel=dict(font_family="IBM Plex Mono, monospace"),
))
pio.templates.default = "plotly_white+brvm"

COULEURS_ACTION = {"VENDRE": "🔴", "ALLÉGER": "🟠", "ACHAT": "🟢", "CONSERVER": "🔵",
                   "SURVEILLER": "🟡", "NEUTRE": "⚪", "ÉCARTÉ": "⚫"}


def config_active() -> dict:
    """config.toml, surchargée par la section [config] des secrets Streamlit.

    En ligne, le disque est effacé à chaque redémarrage : les réglages
    personnels (capital, seuils, filtres) se conservent dans les secrets.
    """
    cfg = charger_config()
    try:
        surcharge = st.secrets.get("config")
        if surcharge:
            cfg = fusionner(cfg, {s: dict(v) for s, v in surcharge.items()})
    except Exception:  # noqa: BLE001 - pas de secrets en local
        pass
    return cfg


def texte_secrets_config(cfg: dict) -> str:
    """Section [config] à coller dans les secrets : seuls les réglages modifiés."""
    base = charger_config()
    lignes = []
    for section, valeurs in cfg.items():
        modifs = {k: v for k, v in valeurs.items() if base.get(section, {}).get(k) != v}
        if modifs:
            lignes.append(f"[config.{section}]")
            lignes += [f"{k} = {_valeur_toml(v)}" for k, v in modifs.items()]
            lignes.append("")
    return "\n".join(lignes)


def style() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page(titre: str, sous_titre: str = "", rubrique: str = "BRVM · aide à la décision") -> dict:
    """En-tête commun : style, verrou, titre, avertissement. Renvoie la config active."""
    style()
    verrou()
    if "cfg" not in st.session_state:
        st.session_state["cfg"] = config_active()
    st.markdown(
        f'<div class="hero"><div class="eyebrow"><span class="dot"></span>{html.escape(rubrique)}</div>'
        f'<h1>{html.escape(titre)}</h1>'
        + (f"<p>{html.escape(sous_titre)}</p>" if sous_titre else "") + "</div>"
        f'<div class="avert"><b>⚠</b><span>{html.escape(AVERTISSEMENT)}</span></div>',
        unsafe_allow_html=True)
    return st.session_state["cfg"]


def ruban(prep: dict, n: int = 40) -> None:
    """Bandeau défilant : dernier cours et variation du jour des titres les plus échangés."""
    mat = prep["matrices"]
    clo = mat["cloture"].dropna(how="all")
    if len(clo) < 2:
        return
    der, veille = clo.iloc[-1], clo.iloc[-2]
    vol = mat["volume_fcfa"].tail(60).median().sort_values(ascending=False)
    elems = []
    for t in vol.index[:n]:
        if pd.isna(der.get(t)) or pd.isna(veille.get(t)) or veille[t] == 0:
            continue
        v = der[t] / veille[t] - 1
        cls, fl = ("up", "▲") if v > 0.0005 else ("dn", "▼") if v < -0.0005 else ("eq", "■")
        cours = f"{der[t]:,.0f}".replace(",", " ")
        elems.append(f'<span class="tk"><b>{t}</b>{cours}<span class="{cls}">{fl} '
                     f'{pct(v, True)}</span></span>')
    piste = "".join(elems)
    st.markdown(f'<div class="tape" aria-label="Cours de la dernière séance"><div class="tape-track">'
                f'{piste}{piste}</div></div>', unsafe_allow_html=True)


def tuiles(elements: list[dict]) -> None:
    """Chiffres clés animés. Chaque élément : label, valeur, ton (buy, sell...), detail."""
    blocs = []
    for i, e in enumerate(elements):
        detail = f'<span class="d">{html.escape(str(e["detail"]))}</span>' if e.get("detail") else ""
        blocs.append(f'<div class="kpi {e.get("ton", "indigo")}" style="animation-delay:{i * 70}ms">'
                     f'<span class="v">{html.escape(str(e["valeur"]))}</span>'
                     f'<span class="l">{html.escape(e["label"])}</span>{detail}</div>')
    st.markdown(f'<div class="kpis">{"".join(blocs)}</div>', unsafe_allow_html=True)


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
    dossiers = [chemin(cfg, d) for d in ("dossier_archive", "dossier_manuel")]
    dossiers.append(DOSSIER_COMPLEMENT)
    fichiers = sorted(p.stat().st_mtime for dossier in dossiers for p in dossier.glob("*.*"))
    return hashlib.md5((json.dumps(cfg, sort_keys=True, default=str)
                        + str(fichiers)).encode()).hexdigest()


@st.cache_data(show_spinner="Préparation des données (contrôle qualité, indicateurs)...")
def _preparer(empreinte: str, cfg_json: str) -> dict:
    return preparer_tout(json.loads(cfg_json))


def donnees(cfg: dict) -> dict:
    return _preparer(_empreinte(cfg), json.dumps(cfg, default=str))


def decisions(cfg: dict) -> dict:
    return decisions_du_jour(donnees(cfg), cfg)


def carte_signal(t: str, r, delai: int = 0) -> None:
    """Carte lisible sur téléphone : signal, chiffres clés et justification complète."""
    ton = TONS_ACTION[r["action"]]
    score = "n.d." if pd.isna(r["score"]) else f"{r['score']:.0f}"
    largeur = 0 if pd.isna(r["score"]) else max(0, min(100, r["score"]))
    cours = f"{r['cours']:,.0f}".replace(",", " ")
    raisons = "".join(f"<li>{html.escape(x)}</li>" for x in str(r["justification"]).split(" ; ") if x)
    st.markdown(
        f'<div class="carte {ton}" style="animation-delay:{delai}ms">'
        f'<div class="tete"><span class="chip">{html.escape(r["action"])}</span>'
        f'<span class="tick">{html.escape(t)}</span><span class="nom">{html.escape(str(r["societe"]))}</span></div>'
        f'<div class="chiffres"><span>Cours <b>{cours}</b></span>'
        f'<span>Score <b>{score}</b><span class="jauge"><i style="width:{largeur}%"></i></span></span>'
        f'<span>Rendement 12 m <b>{pct(r["rendement_12m"])}</b></span>'
        f'<span>Momentum 6 m <b>{pct(r["momentum_6m"], True)}</b></span></div>'
        f'<ul>{raisons}</ul></div>', unsafe_allow_html=True)


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


def bandeau_donnees(prep: dict, avec_ruban: bool = True) -> None:
    if avec_ruban:
        ruban(prep)
    derniere = prep["cours"]["date"].max()
    age = (pd.Timestamp.today().normalize() - derniere).days
    if age > 4:
        st.error(f"Données au **{derniere:%d/%m/%Y}** : données périmées, mets-les à jour dans "
                 "« Paramètres ».")
        return
    note = ("séance du jour ajoutée chaque soir vers 21 h, heure d'Abidjan" if age >= 1
            else "à jour")
    st.markdown(f'<div class="fraicheur"><span class="dot"></span>Données au <b>{derniere:%d/%m/%Y}</b>'
                f'<span class="sep">·</span>{note}</div>', unsafe_allow_html=True)
