"""Pipeline complet de migration Python -> C++ sur un script.

Usage : python main.py [chemin_du_script]      (par défaut data/algorithms.py)

1.  Extraction       (read_extract)          : AST + types (MonkeyType, Pyright) + risque par fonction
2a. Catégorisation   (categorisation_regles) : méthode déterministe, par règles
2b. Catégorisation   (categorisation_llm)    : méthode LLM (+ description)
    -> réponses des deux méthodes dans sortie/metadonnees_<module>.json
3.  Conversion       (conversion)            : C++ fonction par fonction (avec la catégorisation LLM)
4.  Validation       (validation)            : tests d'origine relancés sur le C++ + comparaison des sorties
"""
import json
import shutil
import sys

from categorisation_llm import CONFIG as CONFIG_LLM, categoriser_llm
from categorisation_regles import categoriser_regles
from conversion import SORTIE, convertir
from read_extract import generer_profil_complet
from validation import valider


def titre(texte: str) -> None:
    print(f"\n{'=' * 80}\n {texte}\n{'=' * 80}")


def afficher_profil(profil: dict) -> None:
    identite, archi = profil["identite"], profil["architecture"]
    print(f"Fichier : {identite['fichier']} ({identite['lignes_code']} lignes de code)")
    print(f"Imports : {', '.join(i for i in profil['dependances_cpp'] if i) or 'aucun'}")
    print(f"Complexité estimée : {archi['complexite_estimee']} | imbrication max : {archi['profondeur_imbrication_max']}")
    print(f"Alertes : {', '.join(profil['alertes_globales']) or 'aucune'}")
    print("Fonctions :")
    for nom, f in profil["fonctions"].items():
        params = ", ".join(f"{p['nom']}: {p['type_info']['type']} [{p['type_info']['source']}]" for p in f["parametres"])
        print(f"  - {nom}({params}) -> {f['retour']['type']}   risque {f['risque_conversion_cpp']}")


def afficher_regles(r: dict) -> None:
    tech, metier, cx = r["categorie_technique"], r["categorie_metier"], r["complexite"]
    print(f"Catégorie technique : {', '.join(tech['categories'])}")
    for cat, raisons in tech["raisons"].items():
        print(f"    {cat} <- {', '.join(raisons)}")
    print(f"Catégorie métier    : {metier['categorie']} "
          f"- indices : {', '.join(metier['indices']) or 'aucun mot-clé métier trouvé'}")
    print(f"Complexité          : {cx['niveau']} ({cx['detail']})")


def afficher_llm(cat: dict) -> None:
    d = cat["description"]
    print(f"Lit     : {d['lu']}\nFait    : {d['fait']}\nProduit : {d['produit']}")
    tech, metier, cx = cat["categorie_technique"], cat["categorie_metier"], cat["complexite"]
    print(f"Catégorie technique : {', '.join(tech['categories'])}  ({tech['justification']})")
    print(f"Catégorie métier    : {metier['categorie']} (confiance {metier['confiance']:.2f}) "
          f"- indices : {', '.join(metier['indices'])}")
    print(f"Complexité          : {cx['niveau']} - {cx['justification']}")



def enregistrer_metadonnees(profil: dict, regles: dict, llm: dict) -> None:
    """sortie/metadonnees_<module>.json : réponses aux 4 questions de l'énoncé, par les deux méthodes."""
    q, d = CONFIG_LLM["questions_livrable"], llm["description"]
    metadonnees = {
        "script": profil["identite"]["fichier"],
        "business_categorization": {"question": q["business_categorization"],
                                    "regles": regles["categorie_metier"], "llm": llm["categorie_metier"]},
        "technical_categorization": {"question": q["technical_categorization"],
                                     "regles": regles["categorie_technique"], "llm": llm["categorie_technique"]},
        "complexity": {"question": q["complexity"], "regles": regles["complexite"], "llm": llm["complexite"]},
        "description": {"question": q["description"],
                        "llm": f"{d['fait']} Entrées : {d['lu']}. Sorties : {d['produit']}", "detail": d},
    }
    SORTIE.mkdir(exist_ok=True)
    (SORTIE / f"metadonnees_{profil['identite']['fichier'].removesuffix('.py')}.json").write_text(
        json.dumps(metadonnees, indent=2, ensure_ascii=False), "utf-8")


def afficher_rapport(rapport: dict) -> None:
    t = rapport["totaux"]
    print(f"Modèle : {rapport['modele']} | prompt : {rapport['version_prompt']} "
          f"| catégories utilisées : {', '.join(rapport['categorisation_utilisee']['categories_techniques'])} (LLM)")
    print(f"{t['converti']} convertie(s), {t['échec de compilation']} en échec, {t['sauté']} sautée(s)")
    for f in rapport["fonctions"]:
        print(f"  - {f['fonction']:<20} {f['statut']:<22} {f['tentatives']} tentative(s)"
              + (f"  raison : {f['raison']}" if f["raison"] else ""))
        for h in f.get("hypotheses") or []:
            print(f"        hypothèse : {h}")


def afficher_validation(v: dict) -> None:
    print(f"Compilation du module C++ : {v['compilation'] if v['compilation'] == 'ok' else 'ERREUR'}")
    if v["compilation"] != "ok":
        print(v["compilation"])
        return
    if v["fonctions_restees_python"]:
        print(f"Non converties (testées en Python) : {', '.join(v['fonctions_restees_python'])}")
    tests = v["tests"]
    if tests["fichier"]:
        print(f"Tests {tests['fichier']} sur le C++ : {tests['reussis']}/{tests['total']} réussis")
        for e in tests["echecs"]:
            print(f"  ÉCHEC {e['test']} : {e['message']}")
    else:
        print("Aucun fichier de test trouvé (test_<module>.py)")
    sortie = v["sortie_console"]
    if sortie is not None:
        print(f"Sortie console Python vs C++ : {'identique' if sortie['identique'] else 'DIFFÉRENTE'} "
              f"({sortie['lignes']} lignes)")
        for d in sortie["differences"]:
            print(f"  ligne {d['ligne']} : python={d['python']!r} | cpp={d['cpp']!r}")
    print(f"\nVerdict : {v['verdict'].upper()}")


if __name__ == "__main__":
    chemin = sys.argv[1] if len(sys.argv) > 1 else "data/algorithms.py"

    # On repart d'un dossier sortie/ vide : pas de fichiers d'un run précédent mélangés aux nouveaux
    shutil.rmtree(SORTIE, ignore_errors=True)

    titre("1/ EXTRACTION (read_extract)")
    profil = generer_profil_complet(chemin)
    afficher_profil(profil)

    titre("2a/ CATÉGORISATION DÉTERMINISTE (règles)")
    regles = categoriser_regles(chemin, profil)
    afficher_regles(regles)

    titre("2b/ CATÉGORISATION LLM")
    llm = categoriser_llm(chemin, profil)
    afficher_llm(llm)
    enregistrer_metadonnees(profil, regles, llm)

    titre("3/ CONVERSION EN C++ (catégorisation LLM)")
    rapport = convertir(chemin, profil, llm)
    afficher_rapport(rapport)

    titre("4/ VALIDATION")
    afficher_validation(valider(chemin, rapport))
    print("\nFichiers produits dans sortie/ : metadonnees_* (réponses aux questions), conversion_* (rapport de conversion), "
          "fiches_*, validation_*, cpp/, prompts/")
