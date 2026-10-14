"""Tests de l'analyseur. Les fonctions converties sont testées en C++ à l'étape 4 ;
celles basées sur ast restent en Python (elles sont signalées par la validation)."""
import pytest

from analyse_code import (EXEMPLE, charger_arbre, compter_boucles, compter_branches, compter_lignes_code,
                          est_snake_case, indentation_max, niveau_complexite, noms_fonctions, ratio_commentaires,
                          resume)


@pytest.mark.parametrize("source, attendu", [
    ("", 0),
    ("x = 1\n\n# commentaire\ny = 2\n", 2),
    ("   \n\t\n", 0),
    (EXEMPLE, 8),
])
def test_compter_lignes_code(source, attendu):
    assert compter_lignes_code(source) == attendu


@pytest.mark.parametrize("source, attendu", [
    ("", 0.0),
    ("# a\n# b\n", 1.0),
    ("x = 1\n# note\ny = 2\nz = 3\n", 0.25),
])
def test_ratio_commentaires(source, attendu):
    assert ratio_commentaires(source) == pytest.approx(attendu)


@pytest.mark.parametrize("source, attendu", [
    ("", 0),
    ("x = 1\n", 0),
    ("def f():\n    if x:\n        return 1\n", 2),
    (EXEMPLE, 3),
])
def test_indentation_max(source, attendu):
    assert indentation_max(source) == attendu


@pytest.mark.parametrize("nom, attendu", [
    ("total", True), ("calcul_tva_2", True), ("calculerTotal", False),
    ("_prive", False), ("2eme", False), ("", False),
])
def test_est_snake_case(nom, attendu):
    assert est_snake_case(nom) == attendu


@pytest.mark.parametrize("args, attendu", [((0, 0, 10), "simple"), ((5, 4, 60), "modéré"), ((20, 10, 100), "complexe")])
def test_niveau_complexite(args, attendu):
    assert niveau_complexite(*args) == attendu


def test_fonctions_ast():
    arbre = charger_arbre(EXEMPLE)
    assert noms_fonctions(arbre) == ["total", "remise"]
    assert compter_branches(arbre) == 2
    assert compter_boucles(arbre) == 1


def test_resume():
    assert resume(EXEMPLE) == "2 fonction(s) (total, remise), 8 lignes, complexité simple"
