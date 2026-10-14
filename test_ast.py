import ast
from pathlib import Path

class Extracteur(ast.NodeVisitor):
    def __init__(self):
        # Dictionnaire pour stocker toutes les métriques et signaux demandés
        self.stats = {'fonctions': [], 'imports': [], 'appels': set(), 'io_fichiers': set(),
                      'chaines': set(), 'variables': set(), 'boucles': 0, 'branches': 0, 
                      'dynamique': set(), 'main': False, 'cli': False}

    def visit_Import(self, node): self.stats['imports'].extend(n.name for n in node.names); self.generic_visit(node)
    def visit_ImportFrom(self, node): self.stats['imports'].append(node.module); self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        # Extraction de la signature
        args = [a.arg for a in node.args.args]
        self.stats['fonctions'].append(f"{node.name}({', '.join(args)})")
        
        # Signaux dynamiques dans la déclaration
        if node.args.vararg: self.stats['dynamique'].add("*args")
        if node.args.kwarg: self.stats['dynamique'].add("**kwargs")
        if node.decorator_list: self.stats['dynamique'].add("décorateurs")
        if not all(a.annotation for a in node.args.args): self.stats['dynamique'].add("typage absent")
        self.generic_visit(node)

    def visit_Call(self, node):
        # Détection des appels de fonctions, I/O et exécutions dynamiques
        if isinstance(node.func, ast.Name):
            nom = node.func.id
            self.stats['appels'].add(nom)
            if nom in ('eval', 'getattr'): self.stats['dynamique'].add(nom)
            if nom in ('open', 'read_csv', 'connect', 'requests'): self.stats['io_fichiers'].add(nom)
        self.generic_visit(node)

    def visit_If(self, node):
        self.stats['branches'] += 1 # Métrique de complexité
        try: # Détection ultra-compacte du point d'entrée __main__
            if node.test.left.id == '__name__' and node.test.comparators[0].value == '__main__':
                self.stats['main'] = True
        except AttributeError: pass
        self.generic_visit(node)

    def visit_For(self, node): self.stats['boucles'] += 1; self.generic_visit(node)
    def visit_While(self, node): self.stats['boucles'] += 1; self.generic_visit(node)
    def visit_Yield(self, node): self.stats['dynamique'].add("générateurs"); self.generic_visit(node)
    
    def visit_Constant(self, node):
        # Capture des chaînes (docstrings, requêtes SQL, noms de colonnes)
        if isinstance(node.value, str) and len(node.value) > 2: 
            self.stats['chaines'].add(node.value[:40].replace('\n', ' '))
        self.generic_visit(node)
        
    def visit_Name(self, node):
        self.stats['variables'].add(node.id)
        if node.id in ('sys', 'argparse'): self.stats['cli'] = True # Indices d'arguments terminaux
        self.generic_visit(node)

def analyser_fichier(chemin):
    p = Path(chemin).resolve()
    
    # Lecture classique pour éliminer les commentaires et lignes vides (l'AST ignore les commentaires)
    lignes = [l for l in p.read_text('utf-8').splitlines() if l.strip() and not l.strip().startswith('#')]
    
    visiteur = Extracteur()
    visiteur.visit(ast.parse("\n".join(lignes)))
    s = visiteur.stats
    return s
    # print(s)
    # print(f"--- IDENTITÉ ---\nChemin: {p}\nFichier: {p.name} | Dossier: {p.parent.name}\nLignes de code (hors commentaires): {len(lignes)}")
    # print(f"\n--- STRUCTURE ---\nFonctions: {', '.join(s['fonctions'])}\nPoint d'entrée __main__: {s['main']} | Présence CLI: {s['cli']}")
    # print(f"\n--- IMPORTS & APPELS ---\nModules importés: {', '.join(s['imports']) if s['imports'] else 'Aucun'}")
    # print(f"Appels clés détectés: {', '.join(s['appels'])}")
    # print(f"\n--- ENTRÉES / SORTIES ---\nI/O ou APIs trouvées: {', '.join(s['io_fichiers']) if s['io_fichiers'] else 'Aucune'}")
    # print(f"\n--- INDICES MÉTIER ---\nVariables uniques: {len(s['variables'])} | Noms/Chaînes littérales trouvées: {len(s['chaines'])}")
    # print(f"\n--- MÉTRIQUES ---\nBranches: {s['branches']} | Boucles: {s['boucles']} | Complexité cyclomatique estimée: {1 + s['branches'] + s['boucles']}")
    # print(f"\n--- SIGNAUX DYNAMIQUES ---\n{', '.join(s['dynamique']) if s['dynamique'] else 'Aucun'}")