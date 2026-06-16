"""Simple calculator — contains a deliberate bug for the golden demo."""


def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a + b  # BUG: should be a - b


def multiply(a: int, b: int) -> int:
    return a * b
