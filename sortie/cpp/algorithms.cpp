#include "algorithms.hpp"
#include "pysupport.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <variant>

// is_prime (1 tentative(s))
bool is_prime(int64_t n) {
    if (n <= 1) {
        return false;
    }
    // Calculer la racine carrée. 
    // En Python: int(n**0.5) convertit le float en int (troncature).
    // Pour n >= 2, sqrt(n) > 1. On veut l'intérieur de la boucle range(2, floor(sqrt(n)) + 1).
    // C'est équivalent à i <= floor(sqrt(n)).
    const double root = std::sqrt(static_cast<double>(n));
    const int64_t limit = static_cast<int64_t>(root);
    
    for (int64_t i = 2; i <= limit; ++i) {
        // Python: n % i == 0. 
        // Comme i > 0, le signe du résultat de % en C++ est celui de n.
        // Si n > 0, n % i >= 0. Donc la sémantique est identique à Python pour n positif.
        if (n % i == 0) {
            return false;
        }
    }
    return true;
}

// pgcd (1 tentative(s))
int64_t pgcd(int64_t a, int64_t b) {
    while (b != 0) {
        int64_t r = pysupport::floor_mod(a, b);
        a = b;
        b = r;
    }
    return a;
}

// factorial (1 tentative(s))
int64_t factorial(int64_t n) {
    if (n < 0) {
        throw std::invalid_argument("La factorielle n'est pas définie pour les nombres négatifs.");
    }
    if (n == 0 || n == 1) {
        return 1;
    }
    int64_t result = 1;
    for (int64_t i = 2; i <= n; ++i) {
        result *= i;
    }
    return result;
}

// fibonacci (1 tentative(s))
int64_t fibonacci(int64_t n) {
    if (n < 0) {
        throw std::invalid_argument("L'indice de Fibonacci doit être positif ou nul.");
    }
    if (n == 0) {
        return 0;
    }
    if (n == 1) {
        return 1;
    }
    int64_t a = 0;
    int64_t b = 1;
    for (int64_t i = 2; i <= n; ++i) {
        int64_t next_b = a + b;
        a = b;
        b = next_b;
    }
    return b;
}

// is_palindrome (2 tentative(s))
bool is_palindrome(const std::variant<int64_t, std::string>& s) {
    // 1. Convertir l'entrée en string (str(s))
    std::string s_str;
    if (std::holds_alternative<int64_t>(s)) {
        s_str = std::to_string(std::get<int64_t>(s));
    } else {
        s_str = std::get<std::string>(s);
    }

    // 2. lower()
    std::string s_lower = pysupport::lower(s_str);

    // 3. replace(" ", "") -> supprime les espaces
    std::string s_clean = pysupport::replace(s_lower, " ", "");

    // 4. Vérifier si c'est un palindrome : s_clean == s_clean[::-1]
    std::string s_reversed = s_clean;
    std::reverse(s_reversed.begin(), s_reversed.end());

    return s_clean == s_reversed;
}

// main (1 tentative(s))
// Déclarations forward des fonctions dépendantes
int64_t factorial(int64_t n);
int64_t fibonacci(int64_t n);
bool is_palindrome(const std::variant<int64_t, std::string>& s);
bool is_prime(int64_t n);
int64_t pgcd(int64_t a, int64_t b);

void main_py() {
    std::cout << "--- Exécution des algorithmes ---" << '\n';
    
    // Helper lambda pour convertir bool en string "True"/"False" ou afficher directement
    auto print_bool = [](bool val) {
        std::cout << (val ? "True" : "False");
    };

    std::cout << "Est-ce que 17 est premier ? ";
    print_bool(is_prime(17));
    std::cout << '\n';

    std::cout << "Le PGCD de 48 et 18 est : " << pgcd(48, 18) << '\n';
    
    std::cout << "La factorielle de 5 est : " << factorial(5) << '\n';
    
    std::cout << "Le 7ème nombre de Fibonacci est : " << fibonacci(7) << '\n';

    // is_palindrome attend un variant. On passe une string.
    std::string s = "Elu par cette crapule";
    std::cout << "'Élu par cette crapule' est un palindrome ? ";
    print_bool(is_palindrome(s));
    std::cout << '\n';
}
