"""Fonctions du pipeline qui peuvent être converties en C++ (démo : le pipeline convertit ses propres outils).

Elles sont reprises de read_extract.py, categorisation.py (aujourd'hui categorisation_regles.py) et conversion.py, en fonctions de premier
niveau avec des types précis. Le reste de ces fichiers n'est pas convertible : il dépend de ast,
subprocess, sqlite3 ou de dictionnaires imbriqués sans type.
"""
import re


def decouper(texte: str) -> list[str]:
    """read_extract.PipelineCPlusPlus._decouper : découpe sur les virgules de premier niveau.
    "a: int, b: dict[str, int]" -> ["a: int", "b: dict[str, int]"]"""
    morceaux = []
    profondeur = 0
    courant = ""
    for c in texte:
        if c in "([{":
            profondeur += 1
        elif c in ")]}":
            profondeur -= 1
        if c == "," and profondeur == 0:
            morceaux.append(courant.strip())
            courant = ""
        else:
            courant += c
    if courant.strip():
        morceaux.append(courant.strip())
    return morceaux


def parser_signature(signature: str) -> dict[str, str]:
    """read_extract.PipelineCPlusPlus._parser_signature : signature Pyright -> types.
    "(a: int, b: Unknown = 0) -> bool" -> {"return": "bool", "a": "int", "b": "Unknown"}"""
    profondeur = 0
    fin = len(signature) - 1
    for i, c in enumerate(signature):
        if c == "(":
            profondeur += 1
        elif c == ")":
            profondeur -= 1
            if profondeur == 0:
                fin = i
                break
    types = {"return": signature[fin + 1:].removeprefix(" -> ").strip()}
    for param in decouper(signature[1:fin]):
        nom, _, type_param = param.partition(": ")
        nom = nom.lstrip("*")
        if nom and nom != "/" and type_param:
            types[nom] = type_param.split(" = ")[0]
    return types


def score_risque(nb_types_inconnus: int, retour_inconnu: bool, eval_ou_getattr: bool, args_variables: bool) -> str:
    """read_extract.PipelineCPlusPlus.calculer_risque_fonction, avec des paramètres simples."""
    score = 2 * nb_types_inconnus
    if retour_inconnu:
        score += 2
    if eval_ou_getattr:
        score += 10
    if args_variables:
        score += 3
    if score >= 5:
        return "Élevé"
    if score >= 2:
        return "Moyen"
    return "Faible"


def niveau_complexite(branches_boucles: int, profondeur_max: int, lignes_code: int, nb_imports: int) -> tuple[str, str]:
    """categorisation_regles.complexite (ex complexite_par_regles), avec des paramètres simples -> (niveau, détail du calcul)."""
    base = 1 + branches_boucles
    imbrication = 3 * max(0, profondeur_max - 2)
    taille = lignes_code // 50
    dependances = 2 * nb_imports
    score = base + imbrication + taille + dependances
    if score >= 30:
        niveau = "complexe"
    elif score >= 10:
        niveau = "modéré"
    else:
        niveau = "simple"
    detail = (f"score {score} = branches/boucles {base} + imbrication {imbrication} "
              f"(profondeur max {profondeur_max}) + taille {taille} + dépendances {dependances}")
    return niveau, detail


def compacter(texte: str) -> str:
    """conversion.compacter : retire tous les blancs (comparaison de signatures)."""
    return re.sub(r"\s+", "", texte)


def nom_cpp(nom: str, reserves: list[str]) -> str:
    """conversion.nom_cpp : renomme les noms réservés en C++ (main -> main_py)."""
    if nom in reserves:
        return nom + "_py"
    return nom


def main() -> None:
    # On n'affiche que des chaînes et des nombres : l'affichage d'une liste ou d'un dict est propre à Python
    print("--- Outils du pipeline ---")
    morceaux = decouper("a: int, b: dict[str, int], c: list[str]")
    print(f"decouper : {len(morceaux)} morceaux -> " + " | ".join(morceaux))

    types = parser_signature("(n: int, d: dict[str, int] = {}) -> bool")
    print(f"parser_signature : n={types['n']}, d={types['d']}, retour={types['return']}")

    print(f"score_risque : {score_risque(0, False, False, False)}, {score_risque(1, True, False, False)}, "
          f"{score_risque(0, False, True, False)}")

    niveau, detail = niveau_complexite(5, 3, 120, 1)
    print(f"niveau_complexite : {niveau} ({detail})")

    print(f"compacter : {compacter('int64_t pgcd(int64_t a,  int64_t b)')}")
    print(f"nom_cpp : {nom_cpp('main', ['main', 'new'])}, {nom_cpp('pgcd', ['main', 'new'])}")


if __name__ == "__main__":
    main()
