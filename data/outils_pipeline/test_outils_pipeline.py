"""Tests des outils du pipeline. Ils servent deux fois :
- MonkeyType les exécute pour observer les types réels (étape 1) ;
- les mêmes cas comparent la version Python et la version C++ (étape 4)."""
import pytest

from outils_pipeline import compacter, decouper, niveau_complexite, nom_cpp, parser_signature, score_risque


@pytest.mark.parametrize("texte, attendu", [
    ("a, b, c", ["a", "b", "c"]),
    ("a: int, b: dict[str, int]", ["a: int", "b: dict[str, int]"]),
    ("f(x, y), [1, 2], {3, 4}", ["f(x, y)", "[1, 2]", "{3, 4}"]),
    ("", []),
    ("  seul  ", ["seul"]),
    ("a,,b", ["a", "", "b"]),
])
def test_decouper(texte, attendu):
    assert decouper(texte) == attendu


@pytest.mark.parametrize("signature, attendu", [
    ("(n: int) -> bool", {"return": "bool", "n": "int"}),
    ("(a: Unknown, b: int = 0) -> int", {"return": "int", "a": "Unknown", "b": "int"}),
    ("(d: dict[str, int], *args: str, **kwargs: Any) -> None",
     {"return": "None", "d": "dict[str, int]", "args": "str", "kwargs": "Any"}),
    ("() -> str", {"return": "str"}),
    ("(x, /, y: float) -> float", {"return": "float", "y": "float"}),
])
def test_parser_signature(signature, attendu):
    assert parser_signature(signature) == attendu


@pytest.mark.parametrize("args, attendu", [
    ((0, False, False, False), "Faible"),
    ((1, False, False, False), "Moyen"),
    ((0, True, False, False), "Moyen"),
    ((0, False, False, True), "Moyen"),
    ((2, True, False, False), "Élevé"),
    ((0, False, True, False), "Élevé"),
])
def test_score_risque(args, attendu):
    assert score_risque(*args) == attendu


@pytest.mark.parametrize("args, niveau", [
    ((0, 0, 10, 0), "simple"),
    ((5, 2, 120, 1), "modéré"),
    ((20, 5, 400, 3), "complexe"),
])
def test_niveau_complexite(args, niveau):
    resultat_niveau, detail = niveau_complexite(*args)
    assert resultat_niveau == niveau
    assert detail.startswith("score ")


def test_niveau_complexite_detail():
    assert niveau_complexite(5, 3, 120, 1) == (
        "modéré", "score 13 = branches/boucles 6 + imbrication 3 (profondeur max 3) + taille 2 + dépendances 2")


@pytest.mark.parametrize("texte, attendu", [
    ("int64_t f(int64_t a, int64_t b)", "int64_tf(int64_ta,int64_tb)"),
    ("  a\tb\nc  ", "abc"),
    ("", ""),
])
def test_compacter(texte, attendu):
    assert compacter(texte) == attendu


@pytest.mark.parametrize("nom, attendu", [("main", "main_py"), ("new", "new_py"), ("pgcd", "pgcd")])
def test_nom_cpp(nom, attendu):
    assert nom_cpp(nom, ["main", "new", "delete"]) == attendu
