"""Mini analyseur de code Python (démo des limites de la conversion).

Deux familles de fonctions :
- traitement de texte pur (lignes, indentation, noms) : convertibles en C++ ;
- fonctions basées sur le module ast de Python : pas d'équivalent en C++ (il faudrait réécrire
  un parseur Python complet). Le pipeline les détecte par leur type (ast.Module) et les saute,
  ainsi que les fonctions qui en dépendent.
C'est la même limite que pour read_extract.py, qui repose lui aussi sur ast.
"""
import ast


# --- Traitement de texte pur : convertible ---

def compter_lignes_code(source: str) -> int:
    """Lignes non vides qui ne sont pas des commentaires."""
    total = 0
    for ligne in source.splitlines():
        propre = ligne.strip()
        if propre and not propre.startswith("#"):
            total += 1
    return total


def ratio_commentaires(source: str) -> float:
    """Part des lignes non vides qui sont des commentaires (0.0 si le texte est vide)."""
    non_vides = 0
    commentaires = 0
    for ligne in source.splitlines():
        propre = ligne.strip()
        if propre:
            non_vides += 1
            if propre.startswith("#"):
                commentaires += 1
    if non_vides == 0:
        return 0.0
    return commentaires / non_vides


def indentation_max(source: str) -> int:
    """Niveau d'indentation le plus profond (4 espaces = 1 niveau)."""
    maximum = 0
    for ligne in source.splitlines():
        if not ligne.strip():
            continue
        espaces = 0  # nombre d'espaces en début de ligne
        for c in ligne:
            if c != " ":
                break
            espaces += 1
        maximum = max(maximum, espaces // 4)
    return maximum


def est_snake_case(nom: str) -> bool:
    """Convention de nommage Python : minuscules, chiffres et _, commence par une lettre."""
    if not nom or not nom[0].isalpha():
        return False
    return all(c.islower() or c.isdigit() or c == "_" for c in nom)


def niveau_complexite(nb_branches: int, nb_boucles: int, lignes: int) -> str:
    score = 1 + nb_branches + nb_boucles + lignes // 50
    if score >= 30:
        return "complexe"
    if score >= 10:
        return "modéré"
    return "simple"


# --- Basé sur ast : pas d'équivalent C++ ---

def charger_arbre(source: str) -> ast.Module:
    """Analyse syntaxique du code : produit l'arbre (AST) du module."""
    return ast.parse(source)


def noms_fonctions(arbre: ast.Module) -> list[str]:
    return [n.name for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)]


def compter_branches(arbre: ast.Module) -> int:
    return sum(isinstance(n, (ast.If, ast.IfExp)) for n in ast.walk(arbre))


def compter_boucles(arbre: ast.Module) -> int:
    return sum(isinstance(n, (ast.For, ast.While)) for n in ast.walk(arbre))


def resume(source: str) -> str:
    """Rapport d'une ligne : combine l'analyse ast et le traitement de texte."""
    arbre = charger_arbre(source)
    fonctions = noms_fonctions(arbre)
    lignes = compter_lignes_code(source)
    niveau = niveau_complexite(compter_branches(arbre), compter_boucles(arbre), lignes)
    return f"{len(fonctions)} fonction(s) ({', '.join(fonctions)}), {lignes} lignes, complexité {niveau}"


EXEMPLE = '''# Exemple de script à analyser
def total(prix, quantites):
    somme = 0
    for p, q in zip(prix, quantites):
        if q > 0:
            somme += p * q
    return somme

def remise(montant):
    # 10 % au-delà de 100
    return montant * 0.9 if montant > 100 else montant
'''


def main() -> None:
    print("--- Analyse d'un script ---")
    print(resume(EXEMPLE))
    print(f"Indentation max : {indentation_max(EXEMPLE)}")
    print(f"Commentaires : {ratio_commentaires(EXEMPLE):.2f}")
    print(f"Noms valides : total={est_snake_case('total')}, calculerTotal={est_snake_case('calculerTotal')}")


if __name__ == "__main__":
    main()
