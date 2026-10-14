"""Étape 2b : catégorisation par LLM (Ollama), indépendante des règles.

Le LLM reçoit le code et les faits bruts du profil (imports, types, entrées-sorties), mais PAS les
conclusions de la méthode par règles : les deux méthodes restent indépendantes pour être comparées.
Prompt, modèle et questions de l'énoncé : config/prompts_categorisation.json.
"""
import json
import sys
from pathlib import Path
from typing import Literal

from ollama import Client
from pydantic import BaseModel, Field

client = Client(host="http://100.114.26.31:11434")
CONFIG = json.loads((Path(__file__).resolve().parent / "config" / "prompts_categorisation.json").read_text("utf-8"))
MODELE = CONFIG["modele"]
PROMPT_SYSTEME = "\n".join(CONFIG["prompt_systeme"])
NUM_CTX = 16384

CATEGORIES_TECHNIQUES = Literal[
    "Nettoyage de données", "Transformation de données", "Modélisation / ML", "Reporting / Visualisation",
    "Entrées-sorties / Intégration", "Calcul / Algorithmique", "Tests", "Utilitaire",
]
CATEGORIES_METIER = Literal[
    "Finance", "Ressources humaines", "Supply chain", "Ventes / Marketing",
    "Risque / Conformité", "Pilotage / BI", "Outil technique générique", "Autre",
]
NIVEAUX = Literal["simple", "modéré", "complexe"]


# --- Format de sortie imposé au LLM (Ollama contraint la génération sur ce schéma JSON) ---

class Description(BaseModel):
    lu: str = Field(description="Ce que le script lit en entrée (fichiers, arguments, données)")
    fait: str = Field(description="Les traitements effectués")
    produit: str = Field(description="Ce que le script produit en sortie")

class CategorieTechnique(BaseModel):
    categories: list[CATEGORIES_TECHNIQUES]
    justification: str

class CategorieMetier(BaseModel):
    categorie: CATEGORIES_METIER
    indices: list[str] = Field(description="Éléments précis du code qui justifient la catégorie")
    confiance: float = Field(ge=0, le=1)

class Complexite(BaseModel):
    niveau: NIVEAUX
    justification: str

class Categorisation(BaseModel):
    description: Description
    categorie_technique: CategorieTechnique
    categorie_metier: CategorieMetier
    complexite: Complexite


# --- Prompt ---

def resume_indices(profil: dict) -> str:
    """Faits bruts du profil read_extract, en texte lisible (pas de conclusion de règles)."""
    signatures = []
    for nom, f in profil["fonctions"].items():
        params = ", ".join(f"{p['nom']}: {p['type_info']['type']}" for p in f["parametres"])
        signatures.append(f"  - {nom}({params}) -> {f['retour']['type']}")
    archi = profil["architecture"]
    return "\n".join([
        f"Fichier : {profil['identite']['fichier']} ({profil['identite']['lignes_code']} lignes de code)",
        f"Imports : {', '.join(i for i in profil['dependances_cpp'] if i) or 'aucun'}",
        f"Point d'entrée __main__ : {'oui' if archi['point_entree_main'] else 'non'}",
        f"Interface ligne de commande (sys/argparse) : {'oui' if archi['interface_cli'] else 'non'}",
        f"Branches + boucles : {archi['complexite_estimee'] - 1} | imbrication max : {archi['profondeur_imbrication_max']}",
        f"Signaux dynamiques : {', '.join(profil['alertes_globales']) or 'aucun'}",
        f"Appels d'entrées-sorties : {', '.join(profil['operations']['io_fichiers']) or 'aucun'}",
        "Fonctions (types observés à l'exécution ou inférés) :",
        *signatures,
    ])


def enregistrer_prompt(nom_fichier: str, donnees: dict) -> None:
    """Sauvegarde dans sortie/prompts/ ce qui a été envoyé au LLM (et ce qu'il a répondu).
    Chaque message est découpé en lignes pour rester lisible dans le JSON."""
    def lisible(m): return {"role": m["role"], "lignes": m["content"].splitlines()}
    if "messages" in donnees:
        donnees = {**donnees, "messages": [lisible(m) for m in donnees["messages"]]}
    dossier = Path(__file__).resolve().parent / "sortie" / "prompts"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom_fichier).write_text(json.dumps(donnees, indent=2, ensure_ascii=False), "utf-8")


# --- Appel LLM ---

def categoriser_llm(chemin: str, profil: dict) -> dict:
    code = Path(chemin).read_text("utf-8")[:40000]  # ~10k tokens max, tient dans num_ctx
    message = "\n".join([
        f"=== SCRIPT ({profil['identite']['fichier']}) ===", "```python", code, "```", "",
        "=== INDICES (analyse statique, aide uniquement) ===", resume_indices(profil)])

    messages = [{"role": "system", "content": PROMPT_SYSTEME}, {"role": "user", "content": message}]
    reponse = client.chat(
        model=MODELE,
        messages=messages,
        format=Categorisation.model_json_schema(),  # force un JSON conforme au schéma
        think=False,                                 # pas de raisonnement : plus rapide
        options={"temperature": 0, "num_ctx": NUM_CTX, "num_gpu": 99},
        keep_alive="30m",                            # garde le modèle chargé entre les appels
    )
    if reponse.prompt_eval_count and reponse.prompt_eval_count >= NUM_CTX:
        print(f"[LLM] contexte saturé ({reponse.prompt_eval_count} tokens), script tronqué", file=sys.stderr)
    enregistrer_prompt(f"categorisation_{Path(chemin).stem}.json", {
        "etape": "2b/ catégorisation LLM", "modele": MODELE, "tokens_prompt": reponse.prompt_eval_count,
        "messages": messages + [{"role": "assistant", "content": reponse.message.content}]})
    # Valide la sortie (lève une erreur si le JSON ne respecte pas le schéma)
    return Categorisation.model_validate_json(reponse.message.content).model_dump()


if __name__ == "__main__":
    from read_extract import generer_profil_complet
    chemin = sys.argv[1] if len(sys.argv) > 1 else "data/algorithms.py"
    print(json.dumps(categoriser_llm(chemin, generer_profil_complet(chemin)), indent=4, ensure_ascii=False))
