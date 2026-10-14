"""Étape 2a : catégorisation DÉTERMINISTE (règles, sans LLM).

Les tables de règles sont dans config/regles_categorisation.json.
- Technique : imports et appels relevés par l'AST -> catégories ; beaucoup d'arithmétique -> Calcul
- Métier    : mots-clés métier cherchés dans les noms, chaînes et commentaires du code
- Complexité: score = branches/boucles + imbrication + taille + dépendances
"""
import ast
import json
import re
import unicodedata
from pathlib import Path

REGLES = json.loads((Path(__file__).resolve().parent / "config" / "regles_categorisation.json").read_text("utf-8"))
OPERATIONS_ARITHMETIQUES = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)


def categorie_technique(profil: dict, source: str) -> dict:
    """{catégorie: [raisons]} à partir des imports, des appels et du nombre d'opérations arithmétiques."""
    raisons = {}
    for imp in profil["dependances_cpp"]:
        racine = imp.split(".")[0] if imp else None  # imp = None pour "from . import x"
        if racine in REGLES["etiquettes_imports"]:
            raisons.setdefault(REGLES["etiquettes_imports"][racine], []).append(f"import {imp}")
    appels = set(profil["operations"]["appels"])
    for categorie, noms in REGLES["etiquettes_appels"].items():
        for nom in sorted(appels & set(noms)):
            raisons.setdefault(categorie, []).append(f"appel {nom}()")
    nb_operations = sum(isinstance(n, ast.BinOp) and isinstance(n.op, OPERATIONS_ARITHMETIQUES)
                        for n in ast.walk(ast.parse(source)))
    if nb_operations >= REGLES["seuil_operations_calcul"]:
        raisons.setdefault("Calcul / Algorithmique", []).append(f"{nb_operations} opérations arithmétiques")
    if not raisons:
        raisons[REGLES["categorie_technique_par_defaut"]] = ["aucune règle déclenchée : catégorie par défaut"]
    return {"categories": list(raisons), "raisons": raisons}


def _mots(source: str) -> list:
    """Mots du code en minuscules sans accents ; "calculer_salaireBrut" -> calculer, salaire, brut."""
    source = re.sub(r"([a-z])([A-Z])", r"\1 \2", source)  # camelCase
    source = unicodedata.normalize("NFKD", source).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z]+", source.lower())


def categorie_metier(source: str) -> dict:
    """Compte les mots-clés de chaque domaine ; le domaine le plus cité l'emporte."""
    mots = _mots(source)
    scores, indices = {}, {}
    for domaine, mots_cles in REGLES["mots_cles_metier"].items():
        for cle in mots_cles:
            # Mot-clé long : préfixe (salaire -> salaires) ; court (rh, kpi) : mot exact
            n = sum(m.startswith(cle) if len(cle) >= REGLES["longueur_min_prefixe"] else m == cle for m in mots)
            if n:
                scores[domaine] = scores.get(domaine, 0) + n
                indices.setdefault(domaine, []).append(f"{cle} (x{n})")
    if not scores:  # rien trouvé : catégorie par défaut
        return {"categorie": REGLES["categorie_metier_par_defaut"], "indices": [], "scores": {}}
    gagnant = max(scores, key=scores.get)
    return {"categorie": gagnant, "indices": indices[gagnant], "scores": scores}


def complexite(profil: dict) -> dict:
    archi = profil["architecture"]
    base = archi["complexite_estimee"]                                # 1 + nb if + nb boucles
    imbrication = 3 * max(0, archi["profondeur_imbrication_max"] - 2)  # +3 par niveau au-delà de 2
    taille = profil["identite"]["lignes_code"] // 50                   # +1 par tranche de 50 lignes
    dependances = 2 * len(profil["dependances_cpp"])                   # +2 par import
    score = base + imbrication + taille + dependances
    seuils = REGLES["seuils_complexite"]
    niveau = "complexe" if score >= seuils["complexe"] else "modéré" if score >= seuils["modéré"] else "simple"
    detail = (f"score {score} = branches/boucles {base} + imbrication {imbrication} "
              f"(profondeur max {archi['profondeur_imbrication_max']}) + taille {taille} + dépendances {dependances}")
    return {"niveau": niveau, "score": score, "detail": detail}


def categoriser_regles(chemin: str, profil: dict) -> dict:
    source = Path(chemin).read_text("utf-8")
    return {"categorie_technique": categorie_technique(profil, source),
            "categorie_metier": categorie_metier(source),
            "complexite": complexite(profil)}
