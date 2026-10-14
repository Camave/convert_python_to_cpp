// pysupport.hpp : librairie de support du code C++ converti depuis Python.
// Reproduit les semantiques Python qui different du C++. Copie dans sortie/cpp par conversion.py.
#pragma once

#include <algorithm>
#include <cctype>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <variant>
#include <vector>

namespace pysupport {

// --- Entiers : Python arrondit // vers -inf et % prend le signe du diviseur ; C++ tronque vers 0 ---

inline int64_t floor_div(int64_t a, int64_t b) {
    if (b == 0) throw std::domain_error("division entiere par zero");  // ZeroDivisionError
    int64_t q = a / b;
    if ((a % b != 0) && ((a < 0) != (b < 0))) --q;
    return q;
}

inline int64_t floor_mod(int64_t a, int64_t b) {
    if (b == 0) throw std::domain_error("modulo par zero");
    int64_t r = a % b;
    if (r != 0 && ((r < 0) != (b < 0))) r += b;
    return r;
}

inline double fmod_py(double a, double b) {  // % entre flottants
    if (b == 0.0) throw std::domain_error("modulo par zero");
    double r = std::fmod(a, b);
    if (r != 0.0 && ((r < 0.0) != (b < 0.0))) r += b;
    return r;
}

// --- Entiers : Python n'a pas de limite, int64_t si : on leve std::overflow_error au lieu de deborder ---

inline int64_t checked_add(int64_t a, int64_t b) {
    if ((b > 0 && a > std::numeric_limits<int64_t>::max() - b) ||
        (b < 0 && a < std::numeric_limits<int64_t>::min() - b))
        throw std::overflow_error("depassement int64_t (addition)");
    return a + b;
}

inline int64_t checked_sub(int64_t a, int64_t b) {
    if ((b < 0 && a > std::numeric_limits<int64_t>::max() + b) ||
        (b > 0 && a < std::numeric_limits<int64_t>::min() + b))
        throw std::overflow_error("depassement int64_t (soustraction)");
    return a - b;
}

inline int64_t checked_mul(int64_t a, int64_t b) {
    constexpr int64_t MAX = std::numeric_limits<int64_t>::max(), MIN = std::numeric_limits<int64_t>::min();
    if (a > 0 ? (b > 0 ? a > MAX / b : b < MIN / a)
              : (a < 0 && (b > 0 ? a < MIN / b : b < MAX / a)))
        throw std::overflow_error("depassement int64_t (multiplication)");
    return a * b;
}

inline int64_t ipow(int64_t base, int64_t exposant) {  // ** entre entiers (std::pow passe par un double)
    if (exposant < 0) throw std::invalid_argument("exposant negatif : resultat flottant en Python, utiliser std::pow");
    int64_t r = 1;
    while (exposant > 0) {
        if (exposant & 1) r = checked_mul(r, base);
        exposant >>= 1;
        if (exposant) base = checked_mul(base, base);
    }
    return r;
}

inline int64_t isqrt(int64_t n) {  // math.isqrt, et int(n ** 0.5) sans erreur d'arrondi
    if (n < 0) throw std::domain_error("racine d'un nombre negatif");
    int64_t r = static_cast<int64_t>(std::sqrt(static_cast<double>(n)));
    while (r > 0 && r > n / r) --r;
    while (r + 1 <= n / (r + 1)) ++r;
    return r;
}

// --- Arrondi : round() de Python arrondit au pair (round(0.5) == 0, round(2.5) == 2) ---

inline double round_py(double x, int ndigits) {
    if (ndigits < 0 || !std::isfinite(x)) {  // round(1234.5, -2)
        const double p = std::pow(10.0, -ndigits);
        return std::isfinite(x) ? std::nearbyint(x / p) * p : x;
    }
    // Arrondi sur la valeur binaire exacte, comme Python : round(2.675, 2) == 2.67 (x * 100 donnerait 2.68)
    char buf[400];
    const auto res = std::to_chars(buf, buf + sizeof buf - 1, x, std::chars_format::fixed, ndigits);
    *res.ptr = '\0';
    return std::strtod(buf, nullptr);
}

inline int64_t round_py(double x) { return static_cast<int64_t>(std::nearbyint(x)); }  // round(x) -> int

// --- Chaines (ASCII : 'É'.lower() fonctionne en Python, pas ici) ---

inline std::string rstrip(const std::string& s, const std::string& chars = " \t\n\r\f\v") {
    const auto fin = s.find_last_not_of(chars);
    return fin == std::string::npos ? "" : s.substr(0, fin + 1);
}

inline std::string lstrip(const std::string& s, const std::string& chars = " \t\n\r\f\v") {
    const auto debut = s.find_first_not_of(chars);
    return debut == std::string::npos ? "" : s.substr(debut);
}

inline std::string strip(const std::string& s, const std::string& chars = " \t\n\r\f\v") {
    return lstrip(rstrip(s, chars), chars);
}

inline std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}

inline std::string upper(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
    return s;
}

inline std::string replace(const std::string& s, const std::string& ancien, const std::string& nouveau) {
    if (ancien.empty()) {  // "abc".replace("", "-") == "-a-b-c-"
        std::string r = nouveau;
        for (char c : s) { r += c; r += nouveau; }
        return r;
    }
    std::string r;
    std::size_t debut = 0, pos;
    while ((pos = s.find(ancien, debut)) != std::string::npos) {  // toutes les occurrences, comme Python
        r.append(s, debut, pos - debut).append(nouveau);
        debut = pos + ancien.size();
    }
    return r.append(s, debut, std::string::npos);
}

inline std::string reversed(std::string s) {  // s[::-1] (octet par octet : casse l'UTF-8 multi-octets)
    std::reverse(s.begin(), s.end());
    return s;
}

inline bool startswith(const std::string& s, const std::string& prefixe) { return s.rfind(prefixe, 0) == 0; }

inline bool endswith(const std::string& s, const std::string& suffixe) {
    return s.size() >= suffixe.size() && s.compare(s.size() - suffixe.size(), suffixe.size(), suffixe) == 0;
}

inline std::vector<std::string> split(const std::string& s) {  // str.split() : blancs multiples, sans vides
    std::vector<std::string> r;
    std::size_t i = 0;
    while (i < s.size()) {
        while (i < s.size() && std::isspace(static_cast<unsigned char>(s[i]))) ++i;
        std::size_t j = i;
        while (j < s.size() && !std::isspace(static_cast<unsigned char>(s[j]))) ++j;
        if (j > i) r.push_back(s.substr(i, j - i));
        i = j;
    }
    return r;
}

inline std::vector<std::string> split(const std::string& s, const std::string& sep) {  // str.split(sep)
    if (sep.empty()) throw std::invalid_argument("separateur vide");  // ValueError en Python
    std::vector<std::string> r;
    std::size_t debut = 0, pos;
    while ((pos = s.find(sep, debut)) != std::string::npos) {
        r.push_back(s.substr(debut, pos - debut));
        debut = pos + sep.size();
    }
    r.push_back(s.substr(debut));
    return r;
}

inline std::string join(const std::vector<std::string>& morceaux, const std::string& sep) {
    std::string r;
    for (std::size_t i = 0; i < morceaux.size(); ++i) r += (i ? sep : "") + morceaux[i];
    return r;
}

// --- str() : meme affichage que Python (True/False, 3.0, 1e+16) ---

inline std::string py_str(bool b) { return b ? "True" : "False"; }
inline std::string py_str(const std::string& s) { return s; }
inline std::string py_str(const char* s) { return s; }  // sinon "abc" serait converti en bool

template <class T, std::enable_if_t<std::is_integral_v<T> && !std::is_same_v<T, bool>, int> = 0>
std::string py_str(T n) { return std::to_string(n); }

inline std::string py_str(double x) {  // repr(float) : plus courte representation exacte
    if (std::isnan(x)) return "nan";
    if (std::isinf(x)) return x > 0 ? "inf" : "-inf";
    char buf[64];
    auto res = std::to_chars(buf, buf + sizeof buf, x, std::chars_format::scientific);
    const std::string sci(buf, res.ptr);
    const int exposant = std::atoi(sci.c_str() + sci.find('e') + 1);
    if (exposant >= -4 && exposant < 16)  // Python passe en notation scientifique hors de [1e-4, 1e16[
        res = std::to_chars(buf, buf + sizeof buf, x, std::chars_format::fixed);
    std::string s(buf, res.ptr);
    if (s.find_first_of(".e") == std::string::npos) s += ".0";
    return s;
}

template <class... Ts>
std::string py_str(const std::variant<Ts...>& v) {
    return std::visit([](const auto& x) { return py_str(x); }, v);
}

}  // namespace pysupport
