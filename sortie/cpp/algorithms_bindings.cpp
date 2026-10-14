#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "algorithms.hpp"

PYBIND11_MODULE(algorithms_cpp, m) {
    m.def("is_prime", &is_prime);
    m.def("pgcd", &pgcd);
    m.def("factorial", &factorial);
    m.def("fibonacci", &fibonacci);
    m.def("is_palindrome", &is_palindrome);
    m.def("main", &main_py);
}
