# Aide à la décision BRVM : guide d'utilisation

Application personnelle qui indique quelles actions de la BRVM acheter, quand les vendre,
et pourquoi. Elle ne passe aucun ordre : tu les passes toi-même auprès de Matha Securities.

> Outil d'aide à la décision, pas un conseil en investissement. Les performances passées
> ne préjugent pas des performances futures.

---

## 1. Lancer l'application sur ton ordinateur

**Méthode simple (recommandée)**

1. Installe **Python 3.11 ou plus récent** depuis python.org. Sous Windows, coche
   **« Add python.exe to PATH »** en bas de la première fenêtre d'installation.
2. **Extrais** le fichier zip (clic droit > « Extraire tout »). Ne lance rien depuis
   l'intérieur du zip : cela ne fonctionne pas.
3. Dans le dossier extrait, double-clique sur :
   - **`LANCER_WINDOWS.bat`** sous Windows ;
   - **`LANCER_MAC.command`** sous macOS (la première fois : clic droit > Ouvrir).
4. La première fois, l'installation prend quelques minutes. Ensuite le navigateur s'ouvre
   sur **http://localhost:8501**. Si ce n'est pas le cas, tape cette adresse toi-même.
5. **Laisse la fenêtre noire ouverte** tant que tu utilises l'application : la fermer
   arrête l'application.

**Si ça bloque**

| Ce que tu vois | Que faire |
|---|---|
| « Windows a protégé votre ordinateur » | Cliquer sur « Informations complémentaires », puis « Exécuter quand même ». |
| « Python 3.11 ou plus récent est introuvable » | Installer Python en cochant « Add python.exe to PATH », puis relancer. |
| Le navigateur affiche « Impossible d'accéder au site » | La fenêtre noire a été fermée ou n'a pas fini de démarrer : relancer et attendre 10 secondes. |
| Une erreur pendant l'installation | Vérifier la connexion internet et relancer ; sinon, envoyer une capture de la fenêtre noire. |

**Méthode manuelle** (si tu préfères le terminal)

```bash
cd brvm-decision
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS : source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```
Puis ouvre http://localhost:8501 dans ton navigateur.

---

## 2. Premiers réglages (page « Paramètres »)

1. **Frais** : remplace l'estimation des taxes (0,30 % par défaut) par le taux lu sur ton
   premier avis d'opéré Matha Securities. La commission SGI (0,80 %), la conservation
   (0,25 %/an) et le forfait bourse en ligne (10 000 FCFA/an) viennent déjà de ta grille.
2. **Stratégie** : indique ton capital réel et le nombre de lignes visé.
3. **Filtres personnels** :
   - **Exclusions déontologiques** : inscris les sociétés que tu ne dois pas détenir en
     tant qu'auditeur. Elles n'apparaîtront jamais dans les achats.
   - **Conformité islamique** : active le filtre si tu le souhaites. En mode strict, remplis
     le fichier des états financiers (bouton « Télécharger le fichier de saisie »).
4. Clique sur **« Enregistrer tous les paramètres dans config.toml »** pour les conserver.

Puis, dans **« Mon portefeuille »**, saisis tes positions réelles (titre, date d'achat,
quantité, prix, frais lus sur l'avis d'opéré) et enregistre.

Tes données personnelles sont stockées dans le dossier `donnees_perso/`, qui n'est **jamais
publié** (il est exclu de Git par le fichier `.gitignore`).

---

## 3. Routine conseillée

| Quand | Quoi |
|---|---|
| Chaque semaine (5 minutes) | Paramètres > Données > **Mettre à jour les données**, puis lire « Signaux du jour ». Traiter d'abord les ventes et allègements. |
| Après chaque ordre exécuté | Mettre à jour « Mon portefeuille » avec les chiffres de l'avis d'opéré. |
| Chaque trimestre | Relire le classement, vérifier la page « Qualité des données », relancer le backtest. |
| Chaque année (après publication des comptes) | Mettre à jour le fichier des états financiers. |

Passe tes ordres avec un **cours limite** proche du dernier cours : la liquidité est faible,
et un ordre « au marché » peut s'exécuter loin de ce prix.

---

## 4. Mise à jour et import des données

- **Bouton « Mettre à jour les données »** : télécharge l'archive publique
  ([blakro/brvm](https://github.com/blakro/brvm), licence MIT, mise à jour chaque jour de
  séance), puis complète si besoin les dernières séances depuis Sikafinance.
- **Import manuel** (Paramètres > Données) : un export Sikafinance ou ton propre fichier
  Excel. Les fichiers importés priment toujours sur l'archive.
- **BRVM Composite** : pour le voir dans le backtest, télécharge son historique sur
  Sikafinance (page « Télécharger les cotations de BRVM COMPOSITE ») et importe-le en
  choisissant « Historique du BRVM Composite ».
- **Corrections manuelles** : voir l'onglet « Qualité des données » (divisions de nominal,
  séances erronées, dividendes corrigés).

---

## 5. Mettre l'application en ligne (consultable sur téléphone)

1. Crée un compte sur **github.com** et un **dépôt privé** (Private) ; envoie-y le dossier
   du projet. Le dossier `donnees_perso/` ne part pas, c'est voulu.
2. Va sur **share.streamlit.io**, connecte ton compte GitHub, clique sur « Create app »,
   choisis le dépôt, la branche et le fichier `app.py`.
3. Dans les réglages de l'application, rubrique **Secrets**, colle le contenu de
   `.streamlit/secrets.exemple.toml` adapté :
   - `mot_de_passe` : **obligatoire**, sinon quiconque a le lien voit ton portefeuille ;
   - `exclusions_csv` et `portefeuille_csv` : tes listes au format CSV (la page
     « Mon portefeuille » affiche le texte prêt à copier).
4. Ouvre le lien depuis ton téléphone et ajoute-le à l'écran d'accueil.

En ligne, les modifications faites dans l'application (paramètres, imports) sont perdues
au redémarrage du serveur : reporte-les dans ton dépôt ou dans les secrets.

---

## 6. Ce qui reste manuel

- **Passer les ordres** auprès de Matha Securities.
- **Saisir tes positions** après chaque opération.
- **Saisir les états financiers** (PER, endettement, ratios AAOIFI), une fois par an.
- **Vérifier les anomalies** signalées (sauts de cours inexpliqués, dividendes douteux).
- **Mettre à jour les données** en un clic, en local ou en ligne.
- **Remplacer l'estimation des taxes** par le taux réel de ton avis d'opéré.

---

## 7. Ce que dit le backtest (données au 30/09/2026)

- **2016-2021, marché baissier** : la stratégie reste proche de 0 % par an grâce au filtre
  de tendance et aux stops. Elle fait mieux que 100 % des portefeuilles tirés au hasard,
  dont la médiane perd environ 13 % par an.
- **2022-2026, marché haussier** : environ 26 % par an, contre 28 % pour la référence (tous
  les titres liquides à poids égaux). Elle ne bat qu'environ 30 % des tirages au hasard.
- **Sur toute la période** : rendement proche de la référence (11 % contre 12 % par an),
  mais une **perte maximale deux fois plus faible** (-17 % contre -36 %).

Conclusion : c'est une stratégie **défensive**. Elle protège le capital dans les
mauvaises années, mais n'a pas démontré qu'elle gagne plus que le marché. Relance le
backtest à chaque trimestre : l'application recalcule ces chiffres elle-même.

---

## 8. Structure du projet

```
app.py                 point d'entrée et menu
config.toml            tous les paramètres
vues/                  les 7 pages de l'application
brvm/donnees.py        module 1 : téléchargement, import, stockage SQLite
brvm/qualite.py        module 1 : contrôle qualité, divisions, dividendes, rendement total
brvm/liquidite.py      module 2 : filtre de liquidité
brvm/fondamental.py    module 3 : score composite
brvm/signaux.py        module 4 : règles d'entrée et de sortie
brvm/filtres.py        module 5 : conformité islamique, exclusions déontologiques
brvm/risque.py         module 6 : frais Matha, dimensionnement, portefeuille
brvm/backtest.py       module 7 : simulation, référence, comparaison au hasard
brvm/moteur.py         assemblage des modules
brvm/ui.py             éléments communs de l'interface
donnees/archive/       cours, dividendes, référentiel (archive MIT)
donnees/manuel/        tes imports et corrections (priment sur l'archive)
donnees_perso/         portefeuille, exclusions, états financiers (jamais publiés)
tests/                 17 tests : python -m pytest
```

## 9. Limites connues

- Les montants de dividendes de l'archive sont parfois erronés : environ 1 sur 5 est jugé
  non fiable et écarté, ce qui sous-estime plutôt les rendements passés.
- La correction des dividendes s'appuie sur des montants Sikafinance publiés après coup.
- Les liquidités ne sont pas rémunérées dans la simulation.
- La conformité par ratios AAOIFI n'est pas rejouée dans le backtest (pas d'historique).
- Les appels à Sikafinance dépendent d'un service non officiel qui peut changer.
