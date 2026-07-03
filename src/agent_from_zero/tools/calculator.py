"""Calculator tool — safe math expression evaluation."""

import ast
import math
import operator

# Allowed AST node types (strict whitelist for safety)
_ALLOWED_NODES = {
    ast.Expression,
    ast.Constant,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Tuple,
    ast.List,
}

# Allowed built-in functions
_ALLOWED_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
    "int": int,
    "float": float,
    "sum": sum,
    "len": len,
}

# Allowed constants
_ALLOWED_NAMES = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "nan": math.nan,
}

# Allowed operators
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _validate_node(node: ast.AST) -> None:
    """Recursively validate that the AST only contains allowed node types."""
    if not isinstance(node, tuple(_ALLOWED_NODES)):
        raise ValueError(f"Expression contains a disallowed construct: {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _validate_node(child)


def _eval_node(node: ast.AST) -> float | int:
    """Recursively evaluate a validated AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        op = _ALLOWED_OPS[type(node.op)]
        return op(operand)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op = _ALLOWED_OPS[type(node.op)]
        return op(left, right)
    if isinstance(node, ast.Call):
        func_name = node.func.id if isinstance(node.func, ast.Name) else None
        if func_name is None or func_name not in _ALLOWED_FUNCTIONS:
            raise ValueError(f"Function '{func_name}' is not allowed")
        args = [_eval_node(arg) for arg in node.args]
        return _ALLOWED_FUNCTIONS[func_name](*args)
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        raise ValueError(f"Name '{node.id}' is not allowed")
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval_node(elt) for elt in node.elts]
    raise ValueError(f"Cannot evaluate node: {type(node).__name__}")


def calculator(expression: str) -> str:
    """Safely evaluate a math expression and return the result as a string.

    Only allows basic arithmetic, a whitelist of math functions, and constants.
    Blocks attribute access, imports, and all other potentially dangerous constructs.
    """
    if expression.strip() == "":
        raise ValueError("Empty expression")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(
            f"Cannot evaluate '{expression}'. "
            f"Only arithmetic expressions are supported "
            f"(e.g. '2 + 3 * 4', 'sqrt(16)', 'pi * 2**2'). "
            f"Equations like 'x^2 = 4' and variables are not allowed."
        ) from e

    _validate_node(tree)
    result = _eval_node(tree.body)
    return str(result)
