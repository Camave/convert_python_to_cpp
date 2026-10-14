"""Étape 4 : validation de la conversion.

1. Compile le C++ généré en module Python avec pybind11 (sortie/validation/<module>/<module>_cpp.pyd).
2. Relance les tests d'origine (test_<module>.py à côté du script) sur la version C++ :
   un conftest.py remplace les fonctions converties par leur version C++ ; celles qui n'ont pas
   été converties restent en Python (elles sont signalées).
3. Si main() a été convertie : compare la sortie console du script Python et celle du C++.
"""
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import xml.etree.ElementTree as ET
from pathlib import Path

import pybind11

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "sortie"
GPP = shutil.which("g++")

CONFTEST = """# Généré par validation.py : les tests importent {module}, on leur donne la version C++
import sys, types
sys.path[:0] = [r"{dossier_script}", r"{dossier_validation}"]
import {module} as original
import {module}_cpp as cpp

hybride = types.ModuleType("{module}")
hybride.__dict__.update(original.__dict__)
for nom in {converties!r}:
    setattr(hybride, nom, getattr(cpp, nom))
sys.modules["{module}"] = hybride
"""


def compiler_module(module: str, dossier: Path) -> tuple:
    """g++ -> module Python importable. Renvoie (ok, message)."""
    dossier_cpp = SORTIE / "cpp"
    cible = dossier / f"{module}_cpp{sysconfig.get_config_var('EXT_SUFFIX')}"
    commande = [GPP, "-O2", "-std=c++17", "-shared", f"-I{pybind11.get_include()}",
                f"-I{sysconfig.get_paths()['include']}", f"-I{dossier_cpp}",
                str(dossier_cpp / f"{module}.cpp"), str(dossier_cpp / f"{module}_bindings.cpp")]
    if os.name == "nt":
        # Windows + MinGW : -static évite « DLL load failed », et on lie directement la DLL de Python
        dll = Path(sys.base_prefix) / f"python{sys.version_info.major}{sys.version_info.minor}.dll"
        commande += ["-static", str(dll)]
    else:
        commande += ["-fPIC"]
    res = subprocess.run([*commande, "-o", str(cible)], capture_output=True, text=True)
    return res.returncode == 0, res.stderr[-1500:]


def lancer_tests(chemin: Path, module: str, converties: list, dossier: Path) -> dict:
    """Tests d'origine exécutés sur la version C++, résultat test par test (via junitxml)."""
    fichier_test = chemin.parent / f"test_{module}.py"
    if not fichier_test.exists():
        return {"fichier": None, "total": 0, "reussis": 0, "echecs": []}
    shutil.copy(fichier_test, dossier / fichier_test.name)
    (dossier / "conftest.py").write_text(CONFTEST.format(
        module=module, dossier_script=chemin.parent, dossier_validation=dossier, converties=converties), "utf-8")

    xml = dossier / "resultats.xml"
    subprocess.run([sys.executable, "-m", "pytest", str(dossier), "-q", "-p", "no:cacheprovider",
                    f"--junitxml={xml}"], cwd=dossier, capture_output=True, text=True)
    if not xml.exists():
        return {"fichier": fichier_test.name, "total": 0, "reussis": 0, "echecs": [{"test": "collecte", "message": "pytest n'a pas pu s'exécuter"}]}
    cas = list(ET.parse(xml).getroot().iter("testcase"))
    echecs = []
    for c in cas:
        probleme = c.find("failure")
        if probleme is None:
            probleme = c.find("error")
        if probleme is not None:
            echecs.append({"test": c.get("name"), "message": (probleme.get("message") or "")[:300]})
    return {"fichier": fichier_test.name, "total": len(cas), "reussis": len(cas) - len(echecs), "echecs": echecs}


def comparer_sorties(chemin: Path, module: str, dossier: Path) -> dict:
    """Même programme lancé deux fois : le script Python, puis main() en C++. Comparaison ligne à ligne."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # sinon Python écrit en cp1252 sous Windows
    py = subprocess.run([sys.executable, chemin.name], cwd=chemin.parent, capture_output=True, env=env)
    cpp = subprocess.run([sys.executable, "-c", f"import {module}_cpp; {module}_cpp.main()"],
                         cwd=dossier, capture_output=True, env=env)
    lignes_py = py.stdout.decode("utf-8", "replace").splitlines()
    lignes_cpp = cpp.stdout.decode("utf-8", "replace").splitlines()
    differences = [{"ligne": i + 1, "python": a, "cpp": b}
                   for i, (a, b) in enumerate(zip(lignes_py, lignes_cpp)) if a != b]
    if len(lignes_py) != len(lignes_cpp):
        differences.append({"ligne": "nombre", "python": len(lignes_py), "cpp": len(lignes_cpp)})
    return {"identique": not differences, "lignes": len(lignes_py), "differences": differences,
            # Sorties complètes, pour comparer à l'œil dans validation_<module>.json
            "sortie_python": lignes_py, "sortie_cpp": lignes_cpp,
            "erreurs_python": py.stderr.decode("utf-8", "replace").splitlines(),
            "erreurs_cpp": cpp.stderr.decode("utf-8", "replace").splitlines()}


def valider(chemin: str, rapport_conversion: dict) -> dict:
    chemin = Path(chemin).resolve()
    module = chemin.stem
    dossier = SORTIE / "validation" / module
    shutil.rmtree(dossier, ignore_errors=True)
    dossier.mkdir(parents=True)

    fonctions = rapport_conversion["fonctions"]
    converties = [f["fonction"] for f in fonctions if f["statut"] == "converti"]
    resultat = {"module": module, "fonctions_cpp": converties,
                "fonctions_restees_python": [f["fonction"] for f in fonctions if f["statut"] != "converti"]}

    ok, erreur = compiler_module(module, dossier)
    resultat["compilation"] = "ok" if ok else erreur
    if ok:
        resultat["tests"] = lancer_tests(chemin, module, converties, dossier)
        resultat["sortie_console"] = comparer_sorties(chemin, module, dossier) if "main" in converties else None
        tests_ok = resultat["tests"]["reussis"] == resultat["tests"]["total"]
        sortie_ok = resultat["sortie_console"] is None or resultat["sortie_console"]["identique"]
        resultat["verdict"] = "validé" if tests_ok and sortie_ok else "différences trouvées"
    else:
        resultat["verdict"] = "échec de compilation du module"

    (SORTIE / f"validation_{module}.json").write_text(json.dumps(resultat, indent=2, ensure_ascii=False), "utf-8")
    return resultat


if __name__ == "__main__":
    chemin = sys.argv[1] if len(sys.argv) > 1 else "data/algorithms.py"
    rapport = json.loads((SORTIE / f"conversion_{Path(chemin).stem}.json").read_text("utf-8"))
    print(json.dumps(valider(chemin, rapport), indent=2, ensure_ascii=False))
