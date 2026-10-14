def is_prime(n):
    """Vérifie si un nombre est premier."""
    if n <= 1:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True

def pgcd(a, b):
    """Calcule le Plus Grand Commun Diviseur (PGCD) de deux nombres."""
    while b:
        a, b = b, a % b
    return a

def factorial(n):
    """Calcule la factorielle d'un entier positif."""
    if n < 0:
        raise ValueError("La factorielle n'est pas définie pour les nombres négatifs.")
    if n == 0 or n == 1:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

def fibonacci(n):
    """Retourne le n-ième nombre de la suite de Fibonacci."""
    if n < 0:
        raise ValueError("L'indice de Fibonacci doit être positif ou nul.")
    if n == 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

def is_palindrome(s):
    """Vérifie si une chaîne de caractères (ou un nombre) est un palindrome."""
    s_clean = str(s).lower().replace(" ", "")
    return s_clean == s_clean[::-1]

def main():
    print("--- Exécution des algorithmes ---")
    print(f"Est-ce que 17 est premier ? {is_prime(17)}")
    print(f"Le PGCD de 48 et 18 est : {pgcd(48, 18)}")
    print(f"La factorielle de 5 est : {factorial(5)}")
    print(f"Le 7ème nombre de Fibonacci est : {fibonacci(7)}")
    print(f"'Élu par cette crapule' est un palindrome ? {is_palindrome('Elu par cette crapule')}")

if __name__ == "__main__":
    main()