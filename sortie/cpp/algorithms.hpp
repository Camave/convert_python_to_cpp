#pragma once
#include <cstdint>
#include <string>
#include <vector>
#include <unordered_map>
#include <map>
#include <unordered_set>
#include <optional>
#include <variant>
#include <tuple>
#include <functional>
#include <stdexcept>

bool is_prime(int64_t n);
int64_t pgcd(int64_t a, int64_t b);
int64_t factorial(int64_t n);
int64_t fibonacci(int64_t n);
bool is_palindrome(const std::variant<int64_t, std::string>& s);
void main_py();
