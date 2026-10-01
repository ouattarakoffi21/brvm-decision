import streamlit as st

from brvm import ui
from brvm.risque import taux_aller_retour

cfg = ui.page("Méthodologie")
s, l, f, r = cfg["signaux"], cfg["liquidite"], cfg["fondamental"], cfg["risque"]

st.markdown(f"""
### En une phrase
L'outil cherche des sociétés qui **versent un dividende élevé et régulier**, dont le cours est
**en tendance haussière**, que l'on peut **revendre facilement**, et qui respectent **tes filtres
personnels**. Il te dit aussi quand **sortir**.

### 1. Les données
- **Source** : archive publique des cours de la BRVM depuis 2015 (dépôt GitHub blakro/brvm,
  licence MIT), complétée par Sikafinance et par tes propres imports, qui ont toujours le
  dernier mot.
- **Contrôle qualité** : sur la BRVM, un cours ne peut pas varier de plus d'environ 7,5 % en
  une séance. Tout saut supérieur à {cfg['qualite']['seuil_saut']:.0%} est examiné :
  - s'il se résorbe en quelques séances, c'est une **erreur de saisie** : la séance est écartée ;
  - si le rapport avant/après est un nombre entier (2, 5, 10...), c'est une **division du
    nominal** : tout l'historique antérieur est ajusté ;
  - sinon, le titre est **suspendu {cfg['qualite']['suspension_apres_saut']} séances** et
    signalé pour vérification.
- **Dividendes** : chaque montant est recoupé avec celui publié par Sikafinance. En cas de
  désaccord, on retient le **plus bas**. Un montant non recoupé qui dépasse
  {cfg['qualite']['dividende_suspect']:.0%} du cours est jugé **non fiable** : il n'est pas
  utilisé, et le titre n'a pas de rendement calculable (pas de signal).
- **Rendement total** : les signaux sont calculés sur le cours **dividendes réintégrés**. La
  baisse mécanique du cours le jour du détachement ne déclenche donc jamais de vente.

### 2. La liquidité
Un titre n'est retenu que si, sur les {l['fenetre_seances']} dernières séances, il a été échangé
au moins {l['part_seances_min']:.0%} des séances pour un montant médian d'au moins
{ui.fcfa(l['montant_median_min_fcfa'])} par séance. Chaque achat proposé est limité à
{l['part_max_volume_journalier']:.0%} de ce montant par séance, sur
{l['seances_construction']} séances au plus : sinon, tu risques de ne pas pouvoir revendre.

### 3. Le score (quoi acheter)
Chaque critère est transformé en rang de 0 à 100 parmi les titres comparables, puis pondéré :
| Critère | Poids | Mieux si |
|---|---|---|
| Rendement du dividende sur 12 mois | {f['poids_rendement']:.0%} | plus élevé |
| Régularité (années avec dividende sur {f['annees_regularite']}) | {f['poids_regularite']:.0%} | plus élevée |
| PER (cours / bénéfice par action) | {f['poids_per']:.0%} | plus bas |
| Taux de distribution (dividende / bénéfice) | {f['poids_distribution']:.0%} | plus bas |
| Endettement (dettes / capitaux propres) | {f['poids_endettement']:.0%} | plus bas |

Les trois derniers critères n'existent que si tu as saisi les états financiers. Sans eux, le
score repose sur le rendement et la régularité, et la colonne « Critères disponibles »
l'indique.

### 4. Les signaux (quand acheter, quand vendre)
- **ACHAT** : score au moins égal à {s['score_achat_min']}, moyenne mobile
  {s['mm_courte']} séances au-dessus de la moyenne {s['mm_longue']} séances, et performance
  des {s['momentum_seances']} dernières séances positive.
- **SURVEILLER** : bon score, mais la tendance n'est pas encore favorable.
- **VENDRE** (titre détenu) : repli de {s['stop_suiveur']:.0%} depuis le plus haut atteint
  pendant la détention (stop suiveur), ou moyenne courte passée sous la longue, ou score
  tombé sous {s['score_sortie']}, ou titre exclu par tes filtres.
- **ALLÉGER** : gain de {s['objectif_gain']:.0%} atteint depuis l'achat, dividendes compris.
- **Alerte détachement** : si un dividende est annoncé dans les {s['alerte_detachement_jours']}
  jours, vendre avant te le ferait perdre.

### 5. Les filtres personnels
- **Exclusions déontologiques** : les sociétés que tu inscris (clients audités, conflits
  d'intérêts) n'apparaissent jamais dans les achats.
- **Conformité islamique** (facultative) : exclusion des activités non conformes ; en mode
  strict, vérification des trois ratios AAOIFI (dettes et trésorerie placée à intérêt
  inférieures à 30 % de la capitalisation, revenus non conformes inférieurs à 5 % du chiffre
  d'affaires). Un titre sans données n'est jamais déclaré conforme par défaut.

### 6. Le risque
{r['nombre_lignes_cible']} lignes visées, {r['poids_max_ligne']:.0%} maximum par ligne,
{r['poids_max_secteur']:.0%} maximum par secteur, et un avertissement en dessous de
{r['nombre_lignes_min']} lignes. Un aller-retour coûte environ **{taux_aller_retour(cfg):.1%}**
(grille Matha Securities, commissions de marché et taxes estimées) : c'est pourquoi l'outil
révise peu souvent et ne court pas après les petits écarts.

### 7. Le backtest
Les règles sont rejouées depuis 2016 avec exécution à la séance suivante, frais, dividendes,
droits de garde et contraintes de liquidité. Les paramètres sont choisis sur une première
période et jugés sur une seconde. La stratégie est comparée à des portefeuilles tirés au
hasard dans le même univers : c'est le test le plus honnête, car sur un marché aussi étroit,
beaucoup de méthodes ne font pas mieux que le hasard.

### Ce que l'outil ne fait pas
Il ne passe aucun ordre, ne prévoit pas l'avenir et ne remplace pas la lecture des états
financiers ni l'avis d'un conseiller agréé.
""")
