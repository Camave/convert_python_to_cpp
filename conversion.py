"""Étape 3 : conversion Python -> C++17, fonction par fonction (version simple).

Tous les textes et réglages sont dans config/ :
  prompts_conversion.json  : modèle, rulebook, gabarits de prompt, pièges, éléments interdits
  convertion.json          : correspondance des types Python -> C++
  exemples_conversion.json : exemples Python -> C++ par catégorie
  pysupport.hpp            : librairie de support (// et % de Python, str(), round()...)

Étapes : a. filtrer, b. ordonner, c. signature, d. prompt, e. LLM, f. nettoyer,
         g. vérifier (signature + interdits + g++), h. réparer, i. enregistrer.
"""
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from categorisation_llm import client, enregistrer_prompt

ICI = Path(__file__).resolve().parent
CONFIG = ICI / "config"
SORTIE = ICI / "sortie"

def charger(nom: str) -> dict:
    return json.loads((CONFIG / nom).read_text("utf-8"))

PARAMS = charger("prompts_conversion.json")
TYPES = charger("convertion.json")
EXEMPLES = charger("exemples_conversion.json")["categories"]
MODELE = PARAMS["modele"]
GPP = shutil.which("g++")


# --- a. Filtrer : seules les fonctions « à convertir » et « avec revue » passent ---

def filtrer(profil: dict) -> tuple:
    gardees, sautees = {}, {}
    for nom, f in profil["fonctions"].items():
        statut = PARAMS["statut_filtre"][f["risque_conversion_cpp"]]
        if statut == "bloquante":
            sautees[nom] = f"bloquante (risque {f['risque_conversion_cpp']})"
        else:
            gardees[nom] = statut
    return gardees, sautees


# --- b. Ordonner : une fonction passe après celles qu'elle appelle (parcours en profondeur) ---

def ordonner(profil: dict, noms: list) -> list:
    # Récursion mutuelle : le parcours coupe le cycle ; comme toutes les signatures sont
    # déclarées avant de compiler, chaque membre du groupe voit les autres.
    ordre, vus = [], set()
    def visiter(nom):
        if nom in vus: return
        vus.add(nom)
        for appele in profil["fonctions"][nom].get("appels", []):
            if appele in noms: visiter(appele)
        ordre.append(nom)
    for nom in noms: visiter(nom)
    return ordre


# --- c. Signature : types (convertion.json) + mutation des paramètres (étape 1) ---

def decouper(texte: str, sep: str) -> list:
    """Découpe sur sep au premier niveau : "dict[str, int], str" -> ["dict[str, int]", "str"]."""
    morceaux, profondeur, courant = [], 0, ""
    for c in texte:
        profondeur += (c in "[(") - (c in "])")
        if c == sep and profondeur == 0:
            morceaux.append(courant.strip()); courant = ""
        else:
            courant += c
    return morceaux + [courant.strip()]

def type_cpp(t: str) -> str:
    """"int | None" -> std::optional<int64_t>, "dict[str, list[int]]" -> std::unordered_map<...>"""
    membres = decouper(t.strip(), "|")
    if len(membres) > 1:                                    # union : int | str | None
        autres = [type_cpp(m) for m in membres if m != "None"]
        cpp = autres[0] if len(autres) == 1 else f"std::variant<{', '.join(autres)}>"
        return f"std::optional<{cpp}>" if "None" in membres else cpp
    if "[" not in t:                                        # type simple : int, str...
        if t not in TYPES or re.search(r"\b[TKV]\b", TYPES[t]):
            raise ValueError(f"type non convertible : {t}")
        return TYPES[t]
    base = t[:t.index("[")]                                 # type générique : list[int]
    args = [type_cpp(a) for a in decouper(t[t.index("[") + 1:-1], ",")]
    modele = TYPES.get(base) or next((v for k, v in TYPES.items() if k.startswith(base + "[")), None)
    if modele is None:
        raise ValueError(f"type non convertible : {t}")
    modele = modele.replace("T...", ", ".join(args)).replace("T1, T2", ", ".join(args))
    restants = iter(args)
    modele = re.sub(r"\b[TKV]\b", lambda _: next(restants, "?"), modele)
    if "?" in modele or "Args" in modele:
        raise ValueError(f"type non convertible : {t}")
    return modele

def nom_cpp(nom: str) -> str:
    return f"{nom}_py" if nom in PARAMS["noms_reserves_cpp"] else nom   # main() est réservé en C++

def signature(nom: str, f: dict) -> str:
    params = []
    for p in f["parametres"]:
        t = type_cpp(p["type_info"]["type"])
        if t in PARAMS["types_scalaires"] or p["mutation"] == "reassigne":
            params.append(f"{t} {p['nom']}")            # copie
        elif p["mutation"] == "en_place":
            params.append(f"{t}& {p['nom']}")           # l'appelant voit la modification
        else:
            params.append(f"const {t}& {p['nom']}")     # lecture seule
    retour = "void" if f["retour"]["type"] == "None" else type_cpp(f["retour"]["type"])
    return f"{retour} {nom_cpp(nom)}({', '.join(params)})"


# --- d. Prompt ---

def pieges(node: ast.FunctionDef) -> list:
    """Repère les endroits délicats (lignes du fichier d'origine)."""
    trouves = []
    for n in ast.walk(node):
        cle = type(n.op).__name__ if isinstance(n, ast.BinOp) else type(n).__name__
        if cle in PARAMS["pieges"] and hasattr(n, "lineno"):   # les nœuds opérateurs seuls n'ont pas de ligne
            trouves.append(f"ligne {n.lineno} : {PARAMS['pieges'][cle]}")
    return sorted(set(trouves), key=lambda p: int(p.split()[1]))

def construire_prompt(fiche: dict, code: str, deps: list, exemples: list) -> str:
    texte_fiche = "\n".join([
        f"Fonction : {fiche['fonction']} | risque {fiche['risque']} | {fiche['filtre']}",
        "Types (source) : " + ", ".join(fiche["types"]),
        "Pièges détectés (sois prudent ici) :", *(f"  - {p}" for p in fiche["pieges"] or ["aucun"])])
    texte_exemples = "\n\n".join(
        f"--- {ex['titre']} ---\nPython :\n{ex['python']}\nC++ (programme complet ; toi, écris SEULEMENT la fonction) :\n"
        f"{ex['cpp']}\nPoints d'attention : " + " ; ".join(ex["points_attention"]) for ex in exemples)
    return "\n".join(PARAMS["prompt_fonction"]).format(
        fiche=texte_fiche, code=code, signature=fiche["signature"],
        dependances="\n".join(deps) or "aucune", exemples=texte_exemples or "aucun")


# --- e. LLM / f. Nettoyer ---

def appeler_llm(messages: list) -> str:
    reponse = client.chat(model=MODELE, messages=messages, think=False, keep_alive="30m",
                          options={"temperature": 0, "num_ctx": PARAMS["num_ctx"]})
    return reponse.message.content

def nettoyer(texte: str) -> tuple:
    """Réponse du LLM -> (code, includes, hypothèses)."""
    # On coupe d'abord aux hypothèses : le modèle oublie parfois de fermer le bloc ```
    code, *suite = re.split(r"HYPOTH[EÈ]SES?\s*:", texte, maxsplit=1, flags=re.I)
    code = re.sub(r"^.*?```(?:cpp|c\+\+)?[ \t]*\n", "", code, count=1, flags=re.S)  # texte avant le bloc
    code = code.split("```")[0]                                                        # texte après le bloc
    includes = re.findall(r"^\s*#include\s*<([^>]+)>", code, re.M)
    code = re.sub(r"^\s*#include.*$\n?", "", code, flags=re.M).strip() + "\n"
    hypotheses = [l.strip("-* ").strip() for l in (suite[0] if suite else "").splitlines()
                  if l.strip().startswith(("-", "*"))]
    return code, includes, hypotheses


# --- g. Vérifications rapides ---

def compacter(texte: str) -> str:
    return re.sub(r"\s+", "", texte)

def verifier(code: str, includes: list, sig: str, declarations: list) -> list:
    erreurs = [msg for motif, msg in PARAMS["interdits"].items() if re.search(motif, code)]
    if compacter(sig) not in compacter(code):
        erreurs.append(f"signature modifiée, attendu exactement : {sig}")
    if erreurs:
        return erreurs
    # Compilation seule (syntaxe + types), sans édition de liens ni tests
    entetes = [f"#include <{h}>" for h in sorted(set(PARAMS["entetes_communs"] + includes))]
    source = "\n".join(['#include "pysupport.hpp"', *entetes, *(f"{d};" for d in declarations), code])
    with tempfile.TemporaryDirectory() as tmp:
        fichier = Path(tmp) / "fonction.cpp"
        fichier.write_text(source, "utf-8")
        res = subprocess.run([GPP, "-std=c++17", "-fsyntax-only", f"-I{CONFIG}", str(fichier)],
                             capture_output=True, text=True)
    if res.returncode != 0:
        # Les erreurs + les lignes qui pointent dans le code du modèle (« required from fonction.cpp:23 »)
        lignes = [l for l in res.stderr.splitlines() if "error" in l or "fonction.cpp:" in l]
        erreurs.append("\n".join(lignes)[:2000])
    return erreurs


# --- e. à h. pour une fonction ---

def convertir_fonction(fiche: dict, code_python: str, deps: list, exemples: list) -> list:
    """Complète la fiche ; renvoie toute la conversation (prompts, réponses, réparations)."""
    messages = [{"role": "system", "content": "\n".join(PARAMS["rulebook"])},
                {"role": "user", "content": construire_prompt(fiche, code_python, deps, exemples)}]
    for tentative in range(1, PARAMS["max_reparations"] + 2):
        reponse = appeler_llm(messages)
        messages.append({"role": "assistant", "content": reponse})
        code, includes, hypotheses = nettoyer(reponse)
        erreurs = verifier(code, includes, fiche["signature"], deps)
        fiche.update(tentatives=tentative, code=code, includes=includes, hypotheses=hypotheses, erreurs=erreurs)
        if not erreurs:
            fiche["statut"] = "converti"
            return messages
        # h. Réparer : on renvoie l'erreur au modèle dans la même conversation
        messages.append({"role": "user", "content": "\n".join(PARAMS["prompt_reparation"]).format(
            erreurs="\n".join(erreurs), signature=fiche["signature"])})
    fiche["statut"], fiche["raison"] = "échec de compilation", erreurs[0][:300]
    return messages


# --- i. Enregistrer : fichiers C++, bindings, fiches, rapport ---

def enregistrer(module: str, fiches: list, categories: list) -> dict:
    dossier = SORTIE / "cpp"
    dossier.mkdir(parents=True, exist_ok=True)
    shutil.copy(CONFIG / "pysupport.hpp", dossier / "pysupport.hpp")
    ok = [f for f in fiches if f["statut"] == "converti"]
    entetes = [f"#include <{h}>" for h in PARAMS["entetes_communs"]]

    (dossier / f"{module}.hpp").write_text("\n".join(
        ["#pragma once", *entetes, "", *(f"{f['signature']};" for f in ok), ""]), "utf-8")
    includes = sorted({i for f in ok for i in f["includes"]})
    (dossier / f"{module}.cpp").write_text("\n".join(
        [f'#include "{module}.hpp"', '#include "pysupport.hpp"', *(f"#include <{i}>" for i in includes), "",
         *(f"// {f['fonction']} ({f['tentatives']} tentative(s))\n{f['code']}" for f in ok)]), "utf-8")
    (dossier / f"{module}_bindings.cpp").write_text("\n".join(
        ["#include <pybind11/pybind11.h>", "#include <pybind11/stl.h>", f'#include "{module}.hpp"', "",
         f"PYBIND11_MODULE({module}_cpp, m) {{",
         *(f'    m.def("{f["fonction"]}", &{nom_cpp(f["fonction"])});' for f in ok), "}", ""]), "utf-8")

    (SORTIE / f"fiches_{module}.json").write_text(json.dumps(fiches, indent=2, ensure_ascii=False), "utf-8")
    totaux = {s: sum(f["statut"] == s for f in fiches) for s in ("converti", "échec de compilation", "sauté")}
    rapport = {"module": module, "modele": MODELE, "version_prompt": PARAMS["version_prompt"],
               # Catégorisation LLM utilisée pour choisir les exemples du prompt
               "categorisation_utilisee": {"source": "LLM", "categories_techniques": categories},
               "totaux": totaux,
               "fonctions": [{k: f.get(k) for k in ("fonction", "statut", "raison", "tentatives", "hypotheses")}
                             for f in fiches]}
    (SORTIE / f"conversion_{module}.json").write_text(json.dumps(rapport, indent=2, ensure_ascii=False), "utf-8")
    return rapport


# --- Point d'entrée, à appeler dans main.py après la catégorisation ---

def convertir(chemin: str, profil: dict, categorisation: dict) -> dict:
    source = Path(chemin).read_text("utf-8")
    module = Path(chemin).stem
    noeuds = {n.name: n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    categories = categorisation["categorie_technique"]["categories"]
    # d. 1 ou 2 exemples des catégories du script
    exemples = [ex for cat in categories for ex in EXEMPLES.get(cat, [])][:2]

    gardees, sautees = filtrer(profil)
    fiches = {nom: {"fonction": nom, "statut": "sauté", "raison": raison, "tentatives": 0,
                    "modele": MODELE, "version_prompt": PARAMS["version_prompt"]}
              for nom, raison in sautees.items()}

    # c. Signatures de toutes les fonctions gardées (avant l'ordre, pour les récursions mutuelles)
    signatures = {}
    for nom in list(gardees):
        f = profil["fonctions"][nom]
        try:
            if nom not in noeuds: raise ValueError("méthode ou fonction imbriquée non gérée")
            signatures[nom] = signature(nom, f)
        except ValueError as e:
            fiches[nom] = {"fonction": nom, "statut": "sauté", "raison": str(e), "tentatives": 0}
            del gardees[nom]

    for nom in ordonner(profil, list(gardees)):
        f = profil["fonctions"][nom]
        appeles = [a for a in f.get("appels", []) if a in profil["fonctions"] and a != nom]
        manquantes = [a for a in appeles if a not in gardees]
        fiche = {"fonction": nom, "risque": f["risque_conversion_cpp"], "filtre": gardees[nom],
                 "signature": signatures[nom], "raison": None, "modele": MODELE,
                 "version_prompt": PARAMS["version_prompt"], "pieges": pieges(noeuds[nom]),
                 "types": [f"{p['nom']}: {p['type_info']['type']} ({p['type_info']['source']})" for p in f["parametres"]]
                          + [f"retour: {f['retour']['type']} ({f['retour']['source']})"]}
        fiches[nom] = fiche
        if manquantes:
            fiche.update(statut="sauté", tentatives=0, raison="appelle des fonctions non converties : " + ", ".join(manquantes))
            del gardees[nom]  # ses propres appelants doivent la voir comme non convertie
            continue
        print(f"[conversion] {nom}...", file=sys.stderr)
        deps = [signatures[a] for a in appeles]
        messages = convertir_fonction(fiche, ast.get_source_segment(source, noeuds[nom]), deps, exemples)
        # Un fichier de prompt par fonction : sortie/prompts/conversion_<module>_<fonction>.json
        enregistrer_prompt(f"conversion_{module}_{nom}.json", {
            "etape": "3/ conversion", "fonction": nom, "modele": MODELE, "version_prompt": PARAMS["version_prompt"],
            "statut": fiche["statut"], "tentatives": fiche["tentatives"], "messages": messages})
        # Une fonction en échec fait sauter celles qui l'appellent (traitées après elle)
        if fiche["statut"] != "converti":
            del gardees[nom]

    return enregistrer(module, list(fiches.values()), categories)


if __name__ == "__main__":
    from categorisation_llm import categoriser_llm
    from read_extract import generer_profil_complet
    chemin = sys.argv[1] if len(sys.argv) > 1 else "test_ast.py"
    profil = generer_profil_complet(chemin)
    rapport = convertir(chemin, profil, categoriser_llm(chemin, profil))
    print(json.dumps(rapport, indent=2, ensure_ascii=False))
