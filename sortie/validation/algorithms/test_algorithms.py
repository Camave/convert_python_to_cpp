import pytest
from algorithms import is_prime, pgcd, factorial, fibonacci, is_palindrome

def test_is_prime():
    assert is_prime(17) is True
    assert is_prime(4) is False
    assert is_prime(1) is False
    assert is_prime(-5) is False

def test_pgcd():
    assert pgcd(48, 18) == 6
    assert pgcd(54, 24) == 6
    assert pgcd(7, 3) == 1
    assert pgcd(100, 10) == 10

def test_factorial():
    assert factorial(5) == 120
    assert factorial(0) == 1
    assert factorial(1) == 1
    with pytest.raises(ValueError):
        factorial(-1)

def test_fibonacci():
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(7) == 13
    assert fibonacci(10) == 55
    with pytest.raises(ValueError):
        fibonacci(-2)

def test_is_palindrome():
    assert is_palindrome("Radar") is True
    assert is_palindrome("Python") is False
    assert is_palindrome("Engage le jeu que je le gagne") is True
    assert is_palindrome(12321) is True