"""Chargement et sauvegarde des paramètres (config.toml)."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_CONFIG = RACINE / "config.toml"


def charger_config(chemin: Path | str = CHEMIN_CONFIG) -> dict:
    """Lit le fichier de configuration et renvoie un dictionnaire."""
    with open(chemin, "rb") as f:
        return tomllib.load(f)


def chemin(cfg: dict, cle: str) -> Path:
    """Chemin absolu d'un fichier ou dossier déclaré dans [donnees]."""
    return RACINE / cfg["donnees"][cle]


def _valeur_toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_valeur_toml(x) for x in v) + "]"
    return '"' + str(v).replace('"', '\\"') + '"'


def sauvegarder_config(cfg: dict, chemin_sortie: Path | str = CHEMIN_CONFIG) -> None:
    """Réécrit config.toml (les commentaires d'origine sont perdus)."""
    lignes = ["# Paramètres enregistrés depuis l'application", ""]
    for section, valeurs in cfg.items():
        lignes.append(f"[{section}]")
        for cle, v in valeurs.items():
            lignes.append(f"{cle} = {_valeur_toml(v)}")
        lignes.append("")
    Path(chemin_sortie).write_text("\n".join(lignes), encoding="utf-8")


def fusionner(cfg: dict, modifs: dict) -> dict:
    """Copie de cfg avec les valeurs de modifs (section -> {clé: valeur})."""
    nouveau = copy.deepcopy(cfg)
    for section, valeurs in modifs.items():
        nouveau.setdefault(section, {}).update(valeurs)
    return nouveau
