import math
import ast
from typing import Any

from configs_folder.advanced_settings import _PREPROCESS_REPLACES, _ALLOWED_NODES, _SAFE_NAMES

def _preprocess(expr: str) -> str:
    s = expr
    for k, v in _PREPROCESS_REPLACES.items():
        s = s.replace(k, v)
    return s

def _find_names(node: ast.AST, found: set):
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)

def _check_nodes(node: ast.AST):
    for n in ast.walk(node):
        if not isinstance(n, _ALLOWED_NODES):
            raise ValueError(f"{type(n).__name__}")

def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.Pow):
            return left ** right
        if isinstance(op, ast.LShift):
            return left << right
        if isinstance(op, ast.RShift):
            return left >> right
        if isinstance(op, ast.BitXor):
            return left ^ right
        if isinstance(op, ast.BitAnd):
            return left & right
        if isinstance(op, ast.BitOr):
            return left | right
        raise ValueError(f"BinOp {type(op).__name__}")

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"UnaryOp {type(node.op).__name__}")

    if isinstance(node, ast.Name):
        if node.id in _SAFE_NAMES:
            return _SAFE_NAMES[node.id]
        raise NameError(node.id)

    if isinstance(node, ast.Call):
        func = node.func
        if not isinstance(func, ast.Name):
            raise ValueError("Call must be simple name")
        func_name = func.id
        if func_name not in _SAFE_NAMES:
            raise NameError(func_name)
        fn = _SAFE_NAMES[func_name]
        args = [_eval_node(a) for a in node.args]
        return fn(*args)

    raise ValueError(f"Unsupported node {type(node).__name__}")
