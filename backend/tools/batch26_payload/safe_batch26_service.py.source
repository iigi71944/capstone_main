"""Batch 26: narrow concept-driven edits for input and global dependencies.

Input: prior-imported ``builtins.input(...)`` wrapped by a simple top-level
conversion/print/strip call becomes ``input(...)``. This extends Batch 21,
which handles direct top-level expressions but not nested calls.
Global: a trivial module-level function that reads a literal module constant
in a fixed arithmetic return may declare that read via ``global``. This
extends Batch 23's ``return NAME`` pattern, without altering computations.

AST-only screening, fail-closed source edits. Execution-equivalence checks
remain necessary; this is not a proof of arbitrary Python equivalence.
"""
from __future__ import annotations

import ast

from app.services.improvement.safe_batch21_service import (
    _parse as _parse_b21,
    _span as _span_b21,
    _apply as _apply_b21,
    _binding_safe as _binding_safe_b21,
)

MAX_CHARS = 250_000


def _input_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == 'builtins'
            and node.func.attr == 'input')


def _approved_nested_wrapper(value: ast.AST) -> ast.Call | None:
    # Exactly one nested input, with no arbitrary expression traversal.
    if isinstance(value, ast.Call) and not value.keywords:
        if (len(value.args) == 1 and isinstance(value.func, ast.Name)
                and value.func.id in {'int', 'float', 'str', 'print'}
                and _input_call(value.args[0])):
            return value.args[0]
        if (not value.args and isinstance(value.func, ast.Attribute)
                and value.func.attr == 'strip'
                and _input_call(value.func.value)):
            return value.func.value
    return None


def transform_nested_builtin_input_structure(code: str) -> str:
    """Rename nested builtins.input in *restricted* top-level statements."""
    parsed = _parse_b21(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    imports = [stmt for stmt in tree.body if isinstance(stmt, ast.Import)
               for alias in stmt.names
               if alias.name == 'builtins' and alias.asname is None]
    if len(imports) != 1 or not _binding_safe_b21(tree, {'input', 'builtins'}):
        return code
    edits = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                continue
        elif isinstance(stmt, ast.AnnAssign):
            if not isinstance(stmt.target, ast.Name):
                continue
        elif not isinstance(stmt, ast.Expr):
            continue
        call = _approved_nested_wrapper(stmt.value)
        if call is None or imports[0].lineno >= stmt.lineno:
            continue
        start, end = _span_b21(call.func, offsets)
        if source[start:end] == b'builtins.input':
            edits.append((start, end, b'input'))
    return _apply_b21(code, source, edits)


def transform_readonly_global_calculation(code: str) -> str:
    """Insert a redundant global declaration in pure two-line functions.

    Examples: ``return FACTOR + 1``, ``return FACTOR - 2``, and
    ``return FACTOR * 3``. The module binding is a primitive literal assigned
    before the function; no parameters, closures or side-effecting code.
    """
    if not isinstance(code, str) or not code or len(code) > MAX_CHARS:
        return code
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError, UnicodeError):
        return code
    lines = code.splitlines(keepends=True)
    # Multiple assignments or later name shadows are excluded.
    bindings: dict[str, tuple[int, object]] = {}
    duplicates: set[str] = set()
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Constant)
                and type(stmt.value.value) in (int, float)):
            name = stmt.targets[0].id
            if name in bindings:
                duplicates.add(name)
            bindings[name] = (stmt.lineno, stmt.value.value)
    changes: list[tuple[int, str]] = []
    for stmt in tree.body:
        if not (isinstance(stmt, ast.FunctionDef)
                and not stmt.decorator_list and len(stmt.body) == 1
                and isinstance(stmt.body[0], ast.Return)
                and not stmt.args.posonlyargs and not stmt.args.args
                and not stmt.args.kwonlyargs and stmt.args.vararg is None
                and stmt.args.kwarg is None and not stmt.args.defaults
                and not stmt.args.kw_defaults and stmt.returns is None
                and stmt.end_lineno == stmt.lineno + 1):
            continue
        expr = stmt.body[0].value
        if not (isinstance(expr, ast.BinOp)
                and isinstance(expr.left, ast.Name)
                and isinstance(expr.op, (ast.Add, ast.Sub, ast.Mult))
                and isinstance(expr.right, ast.Constant)
                and type(expr.right.value) is int):
            continue
        name = expr.left.id
        binding = bindings.get(name)
        if (name in duplicates or binding is None or name == stmt.name
                or binding[0] >= stmt.lineno):
            continue
        # Reject all module-level declarations that may rebind a matched name,
        # and any obviously dynamic namespace modification.
        unsafe = False
        for top in tree.body:
            if top is stmt:
                continue
            if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and top.name == name:
                unsafe = True
                break
            if isinstance(top, (ast.Import, ast.ImportFrom)):
                if any((alias.asname or alias.name.split('.')[0]) == name for alias in top.names):
                    unsafe = True
                    break
            if isinstance(top, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                target = top.targets if isinstance(top, ast.Assign) else [top.target]
                if any(isinstance(t, ast.Name) and t.id == name for t in target):
                    if top.lineno != binding[0]:
                        unsafe = True
                        break
            if isinstance(top, ast.Expr) and isinstance(top.value, ast.Call):
                # Conservatively reject arbitrary module call side effects.
                unsafe = True
                break
        if unsafe:
            continue
        operator = '+' if isinstance(expr.op, ast.Add) else '-' if isinstance(expr.op, ast.Sub) else '*'
        lf = lines[stmt.lineno - 1]
        if lf not in (f'def {stmt.name}():\n', f'def {stmt.name}():\r\n'):
            continue
        line = lines[stmt.lineno]
        expected = f'    return {name} {operator} {expr.right.value}'
        if line.rstrip('\r\n') != expected:
            continue
        eol = '\r\n' if lf.endswith('\r\n') else '\n'
        changes.append((stmt.lineno, f'    global {name}{eol}'))
    if not changes:
        return code
    for index, insertion in reversed(changes):
        lines.insert(index, insertion)
    output = ''.join(lines)
    try:
        ast.parse(output)
        return output
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
        return code
