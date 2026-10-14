import ast
import json
import os
import re
import subprocess
import sqlite3
import sys
from pathlib import Path

# Base MonkeyType à côté de ce script (et non relative au dossier courant)
MONKEYTYPE_DB = Path(__file__).resolve().parent / "monkeytype.sqlite3"

# --- 1. EXTRACTEUR AST (Modifié pour retourner des données structurées) ---

# Méthodes qui modifient l'objet sur lequel elles sont appelées (list, dict, set, deque)
METHODES_MUTANTES = {"append", "extend", "insert", "pop", "remove", "clear", "sort", "reverse",
                     "update", "add", "discard", "setdefault", "popitem", "appendleft", "popleft"}

def _racine(expr):
    """p[0].x -> "p" : nom de la variable au bout d'une chaîne d'indexations/attributs."""
    while isinstance(expr, (ast.Subscript, ast.Attribute)): expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None

def detecter_mutations(node_func, noms_params: list) -> dict:
    """{param: "en_place" | "reassigne" | "aucune"} pour choisir le passage en C++ :
    en_place -> T& (l'appelant voit la modification), reassigne -> par valeur, aucune -> const T&."""
    mutation = dict.fromkeys(noms_params, "aucune")
    def marquer(nom, niveau):
        if nom in mutation and mutation[nom] != "en_place": mutation[nom] = niveau

    for n in ast.walk(node_func):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in METHODES_MUTANTES:
            marquer(_racine(n.func.value), "en_place")   # p.append(x)
        cibles = []
        if isinstance(n, ast.Assign): cibles = n.targets
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign, ast.For)): cibles = [n.target]
        elif isinstance(n, ast.Delete): cibles = n.targets
        for cible in cibles:
            for c in ast.walk(cible):
                if isinstance(c, ast.Name) and isinstance(c.ctx, ast.Store):
                    marquer(c.id, "reassigne")             # p = ..., a, b = b, a % b, p += 1
                elif isinstance(c, (ast.Subscript, ast.Attribute)) and isinstance(c.ctx, (ast.Store, ast.Del)):
                    marquer(_racine(c), "en_place")        # p[i] = ..., p.x = ..., del p[k]
    # Limite : "p += [x]" sur une liste est une mutation en place, mais l'AST seul ne connaît pas le type
    return mutation

class Extracteur(ast.NodeVisitor):
    def __init__(self):
        self.stats = {'fonctions': {}, 'imports': [], 'appels': set(), 'io_fichiers': set(),
                      'chaines': set(), 'variables': set(), 'boucles': 0, 'branches': 0, 
                      'dynamique': set(), 'main': False, 'cli': False, 'profondeur_max': 0}
        self.profondeur = 0  # niveau d'imbrication courant (if/for/while/with/try)

    def _visiter_bloc(self, noeuds):
        """Visite un bloc de code un niveau d'imbrication plus bas."""
        self.profondeur += 1
        self.stats['profondeur_max'] = max(self.stats['profondeur_max'], self.profondeur)
        for n in noeuds: self.visit(n)
        self.profondeur -= 1

    def visit_Import(self, node): self.stats['imports'].extend(n.name for n in node.names); self.generic_visit(node)
    def visit_ImportFrom(self, node): self.stats['imports'].append(node.module); self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        args_list = []
        for a in node.args.args:
            # Extraction de l'annotation de type si elle existe dans le code
            annotation = ast.unparse(a.annotation) if a.annotation else None
            args_list.append({"nom": a.arg, "annotation_ast": annotation})
            
        retour_annotation = ast.unparse(node.returns) if node.returns else None
        
        signaux = set()
        if node.args.vararg: signaux.add("*args")
        if node.args.kwarg: signaux.add("**kwargs")
        if node.decorator_list: signaux.add("décorateurs")
        
        mutations = detecter_mutations(node, [a["nom"] for a in args_list])
        for a in args_list: a["mutation"] = mutations[a["nom"]]

        # Sauvegarde structurée de la fonction
        self.stats['fonctions'][node.name] = {
            "parametres": args_list,
            "retour_annotation": retour_annotation,
            "signaux_dynamiques": list(signaux),
            # Fonctions appelées par leur nom (f(...)) : arêtes du graphe d'appels
            "appels": sorted({n.func.id for n in ast.walk(node)
                              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}),
        }
        
        self.stats['dynamique'].update(signaux)
        if not all(a.annotation for a in node.args.args): self.stats['dynamique'].add("typage absent")
        self.generic_visit(node)

    def visit_Call(self, node):
        # f(...) -> "f" ; obj.methode(...) -> "methode" (ex: pd.read_csv, df.dropna)
        nom = None
        if isinstance(node.func, ast.Name): nom = node.func.id
        elif isinstance(node.func, ast.Attribute): nom = node.func.attr
        if nom:
            self.stats['appels'].add(nom)
            if nom in ('eval', 'getattr'): self.stats['dynamique'].add(nom)
            if nom in ('open', 'read_csv', 'read_excel', 'read_json', 'read_sql', 'to_csv', 'to_excel',
                       'to_sql', 'connect', 'urlopen', 'savefig'):
                self.stats['io_fichiers'].add(nom)
        self.generic_visit(node)

    def visit_If(self, node):
        self.stats['branches'] += 1
        try:
            if node.test.left.id == '__name__' and node.test.comparators[0].value == '__main__':
                self.stats['main'] = True
        except AttributeError: pass
        self.visit(node.test)
        self._visiter_bloc(node.body)
        # Un "elif" est un If dans orelse : il reste au même niveau que le if parent
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            self.visit(node.orelse[0])
        elif node.orelse:
            self._visiter_bloc(node.orelse)

    def _visiter_boucle(self, node):
        self.stats['boucles'] += 1
        for champ in ('target', 'iter', 'test'):
            if hasattr(node, champ): self.visit(getattr(node, champ))
        self._visiter_bloc(node.body)
        if node.orelse: self._visiter_bloc(node.orelse)

    def visit_For(self, node): self._visiter_boucle(node)
    def visit_While(self, node): self._visiter_boucle(node)

    def visit_With(self, node):
        for item in node.items: self.visit(item)
        self._visiter_bloc(node.body)

    def visit_Try(self, node):
        self._visiter_bloc(node.body)
        for h in node.handlers: self._visiter_bloc(h.body)
        if node.orelse: self._visiter_bloc(node.orelse)
        if node.finalbody: self._visiter_bloc(node.finalbody)
    def visit_Yield(self, node): self.stats['dynamique'].add("générateurs"); self.generic_visit(node)
    
    def visit_Name(self, node):
        self.stats['variables'].add(node.id)
        if node.id in ('sys', 'argparse'): self.stats['cli'] = True
        self.generic_visit(node)

def analyser_fichier(chemin: str) -> dict:
    """Analyse statique AST et retourne le dictionnaire 's'."""
    p = Path(chemin).resolve()
    lignes = [l for l in p.read_text('utf-8').splitlines() if l.strip() and not l.strip().startswith('#')]
    visiteur = Extracteur()
    visiteur.visit(ast.parse("\n".join(lignes)))
    
    s = visiteur.stats
    s['identite'] = {"chemin": str(p), "fichier": p.name, "lignes_code": len(lignes)}
    # Conversion des sets en listes pour la compatibilité JSON
    s['appels'] = list(s['appels'])
    s['io_fichiers'] = list(s['io_fichiers'])
    s['chaines'] = list(s['chaines'])
    s['variables'] = list(s['variables'])
    s['dynamique'] = list(s['dynamique'])
    
    return s


# --- 2. ENRICHISSEUR ET CONVERTISSEUR (Types & Risques) ---

DEPENDANCE_MAPPING = {
    "numpy": {"cpp_lib": "Eigen", "risque": "Moyen"},
    "pandas": {"cpp_lib": "xtensor", "risque": "Élevé"},
    "math": {"cpp_lib": "<cmath>", "risque": "Faible"},
    "pytest": {"cpp_lib": "GoogleTest", "risque": "Faible"}
}

class PipelineCPlusPlus:
    def __init__(self, donnees_ast: dict, chemin: str):
        self.ast_data = donnees_ast
        self.chemin = chemin
        self.fichier = Path(chemin).resolve()
        self.dossier = self.fichier.parent
        self.module_name = self.fichier.stem

        # Étapes 2 et 3 : MonkeyType et Pyright sont lancés une seule fois au démarrage
        # Format commun : {nom_func: {nom_param: "type", "return": "type"}}
        self.types_monkeytype = self._charger_monkeytype()
        self.types_pyright = self._charger_pyright()

    # --- MonkeyType ---

    def _executer_monkeytype(self):
        """Exécute le code sous MonkeyType pour remplir la base de traces."""
        # Les tests (test_<module>.py) couvrent plus de cas que le main du script
        fichier_test = self.dossier / f"test_{self.module_name}.py"
        if fichier_test.exists():
            cible = ["-m", "pytest", fichier_test.name, "-q"]
        else:
            # Lancé directement, le module est enregistré sous le nom "__main__"
            cible = [self.fichier.name]

        # On efface les anciennes traces du module pour ne pas lire des types périmés
        try:
            with sqlite3.connect(MONKEYTYPE_DB) as conn:
                conn.execute("DELETE FROM monkeytype_call_traces WHERE module IN (?, '__main__')",
                             (self.module_name,))
        except sqlite3.OperationalError:
            pass  # table pas encore créée

        # cwd = dossier du fichier pour que les imports (ex: "from algorithms import ...") marchent,
        # MT_DB_PATH pour que MonkeyType écrive dans notre base et pas dans le dossier courant
        result = subprocess.run(
            [sys.executable, "-m", "monkeytype", "run", *cible],
            cwd=self.dossier, capture_output=True, text=True, check=False,
            env={**os.environ, "MT_DB_PATH": str(MONKEYTYPE_DB)}
        )
        if result.returncode != 0:
            print(f"[MonkeyType] code retour {result.returncode} :\n{result.stdout[-500:]}{result.stderr[-500:]}",
                  file=sys.stderr)

    @staticmethod
    def _formater_type_mt(t: dict) -> str:
        """Convertit le JSON MonkeyType ({"module": "builtins", "qualname": "int"}) en "int"."""
        nom = t["qualname"]
        if nom == "NoneType":
            return "None"
        if t["module"] not in ("builtins", "typing"):
            nom = f"{t['module']}.{nom}"
        elems = [PipelineCPlusPlus._formater_type_mt(e) for e in t.get("elem_types") or []]
        if nom == "Union":
            return " | ".join(elems)
        return f"{nom}[{', '.join(elems)}]" if elems else nom

    def _charger_monkeytype(self) -> dict:
        """Étape 2 : lit toutes les traces du module et fusionne les types observés."""
        self._executer_monkeytype()
        observes = {}  # {func: {param: set(types)}}
        try:
            with sqlite3.connect(MONKEYTYPE_DB) as conn:
                rows = conn.execute("""
                    SELECT qualname, arg_types, return_type
                    FROM monkeytype_call_traces
                    WHERE module IN (?, '__main__')
                """, (self.module_name,)).fetchall()
        except sqlite3.Error as e:
            print(f"[MonkeyType] lecture impossible : {e}", file=sys.stderr)
            return {}

        for qualname, arg_types, return_type in rows:
            # "Classe.methode" -> "methode" (l'AST indexe les fonctions par leur nom court)
            types_func = observes.setdefault(qualname.split(".")[-1], {})
            for param, t in json.loads(arg_types).items():
                types_func.setdefault(param, set()).add(self._formater_type_mt(t))
            # return_type est NULL quand l'appel a levé une exception
            if return_type:
                types_func.setdefault("return", set()).add(self._formater_type_mt(json.loads(return_type)))

        # Plusieurs types observés pour un même paramètre -> union (ex: "int | str")
        return {f: {p: " | ".join(sorted(ts)) for p, ts in params.items()}
                for f, params in observes.items()}

    # --- Pyright ---

    @staticmethod
    def _decouper(texte: str) -> list:
        """Découpe sur les virgules de premier niveau (ignore celles dans [], (), {})."""
        morceaux, profondeur, courant = [], 0, ""
        for c in texte:
            if c in "([{": profondeur += 1
            elif c in ")]}": profondeur -= 1
            if c == "," and profondeur == 0:
                morceaux.append(courant.strip()); courant = ""
            else:
                courant += c
        if courant.strip(): morceaux.append(courant.strip())
        return morceaux

    def _parser_signature(self, signature: str) -> dict:
        """'(a: int, b: Unknown = 0) -> bool' -> {"a": "int", "b": "Unknown", "return": "bool"}"""
        profondeur = 0
        for i, c in enumerate(signature):
            if c == "(": profondeur += 1
            elif c == ")":
                profondeur -= 1
                if profondeur == 0: break
        types = {"return": signature[i + 1:].removeprefix(" -> ").strip()}
        for param in self._decouper(signature[1:i]):
            nom, _, type_param = param.partition(": ")
            nom = nom.lstrip("*")
            if nom and nom != "/" and type_param:
                types[nom] = type_param.split(" = ")[0]
        return types

    def _charger_pyright(self) -> dict:
        """Étape 3 : fait inférer les signatures par Pyright via reveal_type()."""
        # --outputjson ne contient que des diagnostics, pas les types. On ajoute donc
        # reveal_type(f) à une copie du fichier : Pyright émet alors un diagnostic
        # 'Type of "f" is "(n: Unknown) -> bool"' que l'on peut parser.
        source = self.fichier.read_text("utf-8")
        noms = []
        for node in ast.parse(source).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                noms.append(node.name)
            elif isinstance(node, ast.ClassDef):
                noms += [f"{node.name}.{n.name}" for n in node.body
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

        # Copie dans le même dossier pour que Pyright résolve les imports locaux
        copie = self.dossier / f"_pyright_{self.module_name}.py"
        copie.write_text(source + "\n" + "\n".join(f"reveal_type({n})" for n in noms) + "\n", "utf-8")
        try:
            # Pyright via l'interpréteur courant : marche même si le venv n'est pas activé
            result = subprocess.run(
                [sys.executable, "-m", "pyright", "--outputjson", "--pythonpath", sys.executable, str(copie)],
                capture_output=True, text=True, check=False
            )
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"[Pyright] sortie illisible :\n{result.stdout[-500:]}{result.stderr[-500:]}", file=sys.stderr)
            return {}
        finally:
            copie.unlink(missing_ok=True)

        types = {}
        for diag in data.get("generalDiagnostics", []):
            m = re.fullmatch(r'Type of "(.+?)" is "(.*)"', diag["message"])
            if diag["severity"] == "information" and m:
                types[m.group(1).split(".")[-1]] = self._parser_signature(m.group(2))
        return types

    def _appeler_llm_fallback(self, nom_func: str, nom_var: str) -> str:
        """Étape 4 : Placeholder pour l'appel LLM."""
        # TODO: Implémenter l'appel API (OpenAI/Gemini) en lui passant le code de la fonction
        return None

    def resoudre_type(self, nom_var: str, annotation_ast: str, nom_func: str) -> dict:
        """Applique la priorité stricte : AST -> MonkeyType -> Pyright -> LLM -> Unknown"""
        
        # Étape 1 : Annotations dans le code (Priorité absolue)
        if annotation_ast:
            return {"type": annotation_ast, "source": "Annotation"}
        
        # Étape 2 : Vérité terrain d'exécution (MonkeyType)
        type_mt = self.types_monkeytype.get(nom_func, {}).get(nom_var)
        if type_mt:
            return {"type": type_mt, "source": "MonkeyType"}

        # Étape 3 : Analyse statique (Pyright) ; "Unknown" = Pyright n'a pas pu inférer
        type_pr = self.types_pyright.get(nom_func, {}).get(nom_var)
        if type_pr and "Unknown" not in type_pr:
            return {"type": type_pr, "source": "Pyright"}

        # Étape 4 : LLM Fallback (Renvoie None pour l'instant)
        type_llm = self._appeler_llm_fallback(nom_func, nom_var)
        if type_llm:
            return {"type": type_llm, "source": "LLM"}
            
        # Étape 5 : Échec
        return {"type": "Any", "source": "Unknown"}

    def calculer_risque_fonction(self, parametres: list, retour: dict, signaux: list, dynamique_global: list) -> str:
        score = sum(2 for p in parametres if p["type_info"]["source"] == "Unknown")
        if retour["source"] == "Unknown": score += 2
        
        if "eval" in dynamique_global or "getattr" in dynamique_global: score += 10
        if "*args" in signaux or "**kwargs" in signaux: score += 3
        
        if score >= 5: return "Élevé"
        if score >= 2: return "Moyen"
        return "Faible"


# --- 3. FONCTION GLOBALE ORCHESTRATRICE ---

def generer_profil_complet(chemin_fichier: str) -> dict:
    """
    Fonction principale : exécute l'AST, enrichit les types et compile 
    le profil complet prêt pour l'analyse de conversion en C++.
    """
    # 1. Analyse AST initiale
    donnees_ast = analyser_fichier(chemin_fichier)
    
    pipeline = PipelineCPlusPlus(donnees_ast, chemin_fichier)
    profil_final = {
        "identite": donnees_ast["identite"],
        "architecture": {
            "point_entree_main": donnees_ast["main"],
            "interface_cli": donnees_ast["cli"],
            "complexite_estimee": 1 + donnees_ast["branches"] + donnees_ast["boucles"],
            "profondeur_imbrication_max": donnees_ast["profondeur_max"]
        },
        "operations": {
            "appels": sorted(donnees_ast["appels"]),
            "io_fichiers": sorted(donnees_ast["io_fichiers"])
        },
        "dependances_cpp": {},
        "fonctions": {},
        "alertes_globales": donnees_ast["dynamique"]
    }

    # 2. Enrichissement des dépendances
    for imp in donnees_ast["imports"]:
        profil_final["dependances_cpp"][imp] = DEPENDANCE_MAPPING.get(imp, {"cpp_lib": "À définir", "risque": "Inconnu"})

    # 3. Enrichissement des fonctions et calcul du risque
    for nom_func, meta in donnees_ast["fonctions"].items():
        params_enrichis = []
        for p in meta["parametres"]:
            type_info = pipeline.resoudre_type(p["nom"], p["annotation_ast"], nom_func)
            params_enrichis.append({"nom": p["nom"], "type_info": type_info, "mutation": p["mutation"]})
            
        retour_enrichi = pipeline.resoudre_type("return", meta["retour_annotation"], nom_func)
        
        risque = pipeline.calculer_risque_fonction(
            params_enrichis, 
            retour_enrichi, 
            meta["signaux_dynamiques"], 
            donnees_ast["dynamique"]
        )

        profil_final["fonctions"][nom_func] = {
            "parametres": params_enrichis,
            "retour": retour_enrichi,
            "risque_conversion_cpp": risque,
            "signaux_locaux": meta["signaux_dynamiques"],
            "appels": meta["appels"]
        }

    return profil_final

# --- EXÉCUTION ---
if __name__ == "__main__":
    # Test sur le fichier généré au début de notre conversation
    profil = generer_profil_complet("data/algorithms.py")
    
    # Affichage propre en JSON
    print(json.dumps(profil, indent=4, ensure_ascii=False))