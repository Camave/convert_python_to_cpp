# Généré par validation.py : les tests importent algorithms, on leur donne la version C++
import sys, types
sys.path[:0] = [r"C:\perso\projet\projet_python\deloitte\case\data", r"C:\perso\projet\projet_python\deloitte\case\sortie\validation\algorithms"]
import algorithms as original
import algorithms_cpp as cpp

hybride = types.ModuleType("algorithms")
hybride.__dict__.update(original.__dict__)
for nom in ['is_prime', 'pgcd', 'factorial', 'fibonacci', 'is_palindrome', 'main']:
    setattr(hybride, nom, getattr(cpp, nom))
sys.modules["algorithms"] = hybride
