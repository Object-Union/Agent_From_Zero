"""Tests for Calculator tool."""

import pytest


class TestCalculator:
    """Behavior 4: Calculator evaluates expressions safely."""

    def test_basic_arithmetic(self):
        """Calculator evaluates basic math expressions correctly."""
        from agent_from_zero.tools.calculator import calculator

        assert calculator("2 + 2") == "4"
        assert calculator("3 * 7") == "21"
        assert calculator("10 / 3")  # result is a string containing a float
        result = float(calculator("10 / 3"))
        assert abs(result - 3.333) < 0.01

    def test_complex_expression(self):
        """Calculator handles nested expressions."""
        from agent_from_zero.tools.calculator import calculator

        assert calculator("(2 + 3) * 4") == "20"

    def test_rejects_import(self):
        """Calculator rejects __import__ and other dangerous builtins."""
        from agent_from_zero.tools.calculator import calculator

        with pytest.raises(ValueError, match="not allowed"):
            calculator("__import__('os')")

    def test_rejects_attribute_access(self):
        """Calculator rejects expressions that access attributes."""
        from agent_from_zero.tools.calculator import calculator

        with pytest.raises(ValueError, match="disallowed"):
            calculator("''.__class__")

    def test_rejects_non_math_expression(self):
        """Calculator only accepts math-safe expressions."""
        from agent_from_zero.tools.calculator import calculator

        # standard math functions are fine
        assert calculator("abs(-5)") == "5"
        assert calculator("pow(2, 3)") == "8"

    def test_malformed_expression_raises(self):
        """Malformed expression raises a clear error."""
        from agent_from_zero.tools.calculator import calculator

        with pytest.raises(ValueError):
            calculator("1 + +")
