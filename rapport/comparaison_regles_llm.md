# Comparaison des méthodes de catégorisation : règles vs LLM

## 1. Objectif et protocole

L'énoncé demande d'extraire, pour chaque script, la catégorie métier, la catégorie technique et la complexité, par deux méthodes indépendantes, puis de comparer les résultats.

| | Méthode par règles (`categorisation_regles.py`) | Méthode LLM (`categorisation_llm.py`) |
|---|---|---|
| Métier | mots-clés par domaine comptés dans le code (noms, chaînes, commentaires) ; le domaine le plus cité l'emporte | choix dans une liste fermée de 8 domaines, avec indices et confiance auto-déclarée |
| Technique | imports et appels reconnus (`pandas`, `dropna`, `fit`…) + seuil d'opérations arithmétiques | choix d'une ou plusieurs catégories dans une liste fermée de 8, avec justification |
| Complexité | score = branches/boucles + imbrication + taille + dépendances, seuils 10 / 30 | jugement du modèle (simple / modéré / complexe), avec justification |
| Description | aucune (non requise par l'énoncé pour la méthode déterministe) | lu / fait / produit |

**Indépendance des méthodes** : le LLM reçoit le code et les faits bruts de l'analyse statique (imports, types, nombre de branches), mais **pas** les conclusions des règles. Une première version lui donnait le niveau de complexité calculé par les règles : il le reprenait presque toujours (sur `algorithms.py`, il répondait « modéré » avec cette information et « simple » sans). On a donc retiré cette information pour éviter de l'ancrer sur la réponse des règles.

**Jeu de test** : 12 scripts Python du projet (30 à 330 lignes) : les 4 scripts de `data/` et les 8 modules du pipeline. Ils couvrent des profils variés : calcul pur, tests pytest, entrées-sorties (sqlite, fichiers), sous-processus, appels à un LLM.

**Modèle** : `qwen3.5:9b` via Ollama, température 0, sortie contrainte par un schéma JSON.

**Résultats bruts** : `rapport/comparaison_methodes.json`.

## 2. Résultats globaux

| Indicateur | Valeur |
|---|---|
| Accord métier (même catégorie) | 3 / 12 (25 %) |
| Bonne réponse métier, règles * | 4 / 12 (33 %) |
| Bonne réponse métier, LLM * | **9 / 12 (75 %)** |
| Technique : catégorie principale identique | 4 / 12 (33 %) |
| Technique : recouvrement moyen des listes (Jaccard) | 0,45 |
| Accord complexité | 6 / 12 (50 %) |
| Désaccords de complexité où le LLM est plus bas | **6 / 6** |
| Temps moyen par script | règles 0,05 s, LLM 7,8 s (environ 170 fois plus) |

\* Vérité terrain : les 12 scripts sont des outils techniques internes, sans domaine métier. La bonne réponse est donc « Outil technique générique » pour tous.

## 3. Résultats script par script

| Script | Lignes | Métier, règles | Métier, LLM (confiance) | Technique, règles | Technique, LLM | Complexité, règles (score) | Complexité, LLM |
|---|---|---|---|---|---|---|---|
| data/algorithms.py | 48 | générique ✔ | générique ✔ (0,95) | Utilitaire, Calcul | Calcul | modéré (13) | simple |
| data/test_algorithms.py | 30 | générique ✔ | RH ✘ (0,10) | Tests | Tests, Utilitaire | simple (5) | simple |
| data/outils_pipeline/outils_pipeline.py | 97 | Risque ✘ | générique ✔ (0,95) | Transformation, Utilitaire, Calcul | Utilitaire | modéré (27) | simple |
| data/outils_pipeline/test_outils_pipeline.py | 57 | Risque ✘ | RH ✘ (0,30) | Tests, Utilitaire | Tests | simple (6) | simple |
| read_extract.py | 329 | Risque ✘ | générique ✔ (0,95) | E/S, Transformation, Utilitaire, Calcul | Utilitaire, ML | complexe (100) | complexe |
| categorisation_regles.py | 67 | RH ✘ | générique ✔ (0,30) | Utilitaire, Calcul | Calcul, Utilitaire | modéré (25) | modéré |
| categorisation_llm.py | 95 | Ventes ✘ | générique ✔ (0,95) | Transformation, Calcul | Utilitaire, ML | modéré (20) | simple |
| conversion.py | 235 | Risque ✘ | générique ✔ (0,95) | Transformation, Utilitaire, Calcul | Transformation, Utilitaire | complexe (57) | modéré |
| validation.py | 108 | générique ✔ | générique ✔ (0,95) | Calcul | Tests, Calcul | complexe (30) | modéré |
| main.py | 112 | Ventes ✘ | Supply chain ✘ (0,45) | Transformation, Utilitaire | ML, Transformation | complexe (30) | modéré |
| test_ast.py | 49 | Supply chain ✘ | générique ✔ (0,90) | Transformation, Utilitaire | Utilitaire, Reporting | modéré (15) | modéré |
| comparer_methodes.py | 73 | générique ✔ | générique ✔ (0,90) | Utilitaire, Calcul | Utilitaire | modéré (19) | modéré |

## 4. Analyse

### 4.1 Catégorie métier : avantage net au LLM

**Les règles se trompent sur un mot isolé, pris hors contexte.** Les 8 erreurs viennent toutes de mots-clés ambigus :
- « risque » (risque *de conversion*) donne « Risque / Conformité », 4 fois ;
- « client » (le client Ollama) et « produit » (le champ « ce que le script produit ») donnent « Ventes / Marketing » ;
- « stock » donne « Supply chain » ;
- « salaire », cité dans un commentaire d'exemple, donne « Ressources humaines ».

Il suffit d'une occurrence pour décider (`test_ast.py` : un seul « stock »). La méthode ne fait pas la différence entre le vocabulaire du domaine et le vocabulaire technique.

**Le LLM comprend le rôle du code.** Ses indices sont souvent bien choisis : « conversion Python → C++17 », « g++ », « pybind11 » pour `conversion.py`. Ses 3 erreurs ont un point commun : **une confiance basse (0,10 à 0,45)**, alors que les bonnes réponses sont en général à 0,90-0,95. Quand il ne trouve pas de domaine, il force une catégorie de la liste (« RH » pour un fichier de tests) au lieu de répondre « générique », mais **sa confiance signale l'erreur**. Une seule bonne réponse a aussi une confiance basse (0,30).

**Biais du jeu de test** : les scripts du pipeline *parlent* de catégorisation. `categorisation_llm.py` contient littéralement « Ressources humaines », « Ventes / Marketing ». Ce vocabulaire piège les règles plus que ne le ferait un script métier ordinaire. À l'inverse, le jeu ne contient **aucun vrai script métier** : on n'a donc pas pu vérifier que les règles reconnaissent bien un script de paie ou de facturation, ce qui devrait être leur point fort.

### 4.2 Catégorie technique : deux méthodes imparfaites, aux erreurs différentes

**Erreurs typiques des règles** :
- **Faux positifs de nom** : `join()` est rangé dans « Transformation de données » (le `join` de pandas), alors qu'il s'agit presque toujours de `" ".join(...)` sur des chaînes. C'est la cause des 6 « Transformation » des règles. Sans le type de l'objet, la règle ne peut pas les distinguer.
- **Seuil arithmétique trop bas** : 5 opérations suffisent à ajouter « Calcul / Algorithmique », et des compteurs ou des indices (`i + 1`) l'atteignent vite (8 scripts sur 12).
- **Oublis** : les sous-processus (`subprocess`), l'écriture de fichiers (`write_text`) et le lancement de pytest ne sont pas dans les tables. `validation.py`, qui lance des tests, n'est pas classé « Tests ».
- **Points forts** : les signaux clairs sont fiables (`import pytest` donne « Tests », `import sqlite3` donne « Entrées-sorties »), et chaque catégorie est **justifiée par l'élément exact** qui l'a déclenchée.

**Erreurs typiques du LLM** :
- **Sur-interprétation** : « Modélisation / ML » pour trois scripts qui *appellent* un LLM ou *analysent* du code (`read_extract.py`, `main.py`, `categorisation_llm.py`), et « Reporting / Visualisation » pour `test_ast.py`, qui n'affiche rien.
- **Oublis** : les entrées-sorties de `read_extract.py` (sqlite, sous-processus) ne sont pas relevées, alors que les règles les trouvent.
- **Points forts** : il identifie mieux la catégorie *principale* (« Calcul » pour `algorithms.py`, « Tests » pour les fichiers de tests, « Utilitaire » pour les outils de chaînes).

Le recouvrement moyen n'est que de 0,45, et les erreurs ne se recoupent pas : les deux méthodes sont **complémentaires** sur cette dimension.

### 4.3 Complexité : un désaccord systématique

Les deux méthodes s'accordent 6 fois sur 12, et **à chaque désaccord le LLM donne un niveau plus bas** que les règles.

**Cause côté règles** : le score additionne les branches de **tout le fichier**, ajoute 2 points par import (y compris `os` ou `sys`) et 1 point par tranche de 50 lignes. Un fichier qui contient beaucoup de fonctions simples obtient donc un score élevé. Exemple : `algorithms.py` atteint 13 (modéré) avec 5 fonctions de 5 lignes chacune.

**Cause côté LLM** : il raisonne fonction par fonction (« fonctions courtes et indépendantes, logique linéaire ») et tend à sous-estimer les fichiers longs. Exemple : `conversion.py`, 235 lignes, avec un tri des dépendances et une boucle de réparation par LLM, est jugé seulement « modéré ».

Aucune des deux n'a raison partout. `algorithms.py` est plus justement « simple » (LLM), tandis que `conversion.py` est plus justement « complexe » (règles). Les seuils des règles (10 / 30) ont été fixés a priori et ne sont pas calibrés.

### 4.4 Critères transverses

| Critère | Règles | LLM |
|---|---|---|
| Temps | 0,05 s par script | 7,8 s par script |
| Reproductibilité | totale | bonne à température 0, mais dépend du modèle et du prompt (une mise à jour du modèle peut changer les réponses) |
| Explicabilité | exacte : l'élément du code qui a déclenché chaque décision | justification en texte libre, plausible mais invérifiable automatiquement |
| Compréhension du contexte | aucune (mot isolé) | bonne (rôle du code) |
| Maintenance | listes de mots-clés et seuils à enrichir à la main | prompt à ajuster ; aucune liste à maintenir |
| Description du script | impossible | oui |

## 5. Conclusion et recommandations

1. **Utiliser le LLM pour le métier et la description**, là où la compréhension du contexte est indispensable. Envoyer en **revue humaine** toute réponse dont la confiance est inférieure à 0,5 : sur ce jeu, cette règle aurait intercepté les 3 erreurs métier du LLM, au prix d'une seule bonne réponse vérifiée inutilement.
2. **Garder les règles comme socle déterministe pour la technique et la complexité**, et comme garde-fou : elles sont rapides, reproductibles et auditables. Les signaux forts (imports de bibliothèques métier ou de test) sont fiables.
3. **Améliorations des règles mises en évidence par cette comparaison** :
   - **Métier** : exiger au moins deux mots-clés distincts, chercher en priorité dans les chaînes et les noms de fichiers lus, et ignorer le vocabulaire technique courant (`client`, `risque` hors contexte).
   - **Technique** : distinguer `str.join` de `DataFrame.join` grâce aux types de l'étape 1 ; ajouter `subprocess`, `write_text` et `pytest` lancé en sous-processus ; relever le seuil arithmétique ou le rapporter à la taille du fichier.
   - **Complexité** : calculer le score **par fonction** et garder le maximum plutôt que la somme sur le fichier ; ne compter que les dépendances externes ; calibrer les seuils sur un échantillon étiqueté.
4. **Combiner les deux méthodes** quand elles sont d'accord. Les cas d'accord (25 % pour le métier, 50 % pour la complexité) sont les plus sûrs ; les désaccords désignent précisément les scripts à relire.

## 6. Limites de cette étude

- **Petit échantillon** : 12 scripts, tous issus du même projet et tous techniques. Il n'y a **aucun script métier réel** (finance, RH, ventes) : c'est la première chose à ajouter pour une évaluation représentative.
- **Vérité terrain** : elle est établie à la main, et seulement pour le métier. Pour la technique et la complexité, l'analyse porte sur les erreurs manifestes et les biais, pas sur un taux de bonnes réponses.
- **Un seul modèle** (`qwen3.5:9b`) : le modèle plus grand utilisé pour la conversion (`qwen3.6:35b-a3b`) n'a pas été évalué ici.
- **Types simplifiés** : MonkeyType a été désactivé pour cette comparaison, car il exécuterait le pipeline lui-même. Les types proviennent donc uniquement des annotations et de Pyright. L'effet sur la catégorisation est négligeable.
