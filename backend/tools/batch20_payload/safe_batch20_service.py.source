"""Batch 20: two conservative style-directed source edits.

None tag: `result = {}.get(CONSTANT)` -> `result = None`, for an exact empty
literal dictionary whose key cannot have side effects.
Print tag: top-level `builtins.print(...)` -> `print(...)` only with a prior
unique direct import and with no detectable shadowing or dynamic rebinding.

These are local syntax rewrites, not universal execution-equivalence proofs.
The external style application verifier remains authoritative.
"""
from __future__ import annotations

import ast

_MAX_LENGTH = 250_000
_FORBIDDEN_DYNAMIC_CALLS = frozenset({
    'globals', 'locals', 'vars', 'exec', 'eval', '__import__',
    'setattr', 'delattr',
})


def _read(code: str):
    if not isinstance(code, str) or not code or len(code) > _MAX_LENGTH:
        return None
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, TypeError, UnicodeError, RecursionError, MemoryError):
        return None
    offsets = [0]
    for line in code.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    return tree, code.encode('utf-8'), offsets


def _span(node: ast.AST, offsets: list[int]):
    return offsets[node.lineno - 1] + node.col_offset, offsets[node.end_lineno - 1] + node.end_col_offset


def _finish(code: str, source: bytes, edits):
    if not edits:
        return code
    last_start = len(source) + 1
    for start, end, replacement in sorted(edits, reverse=True):
        if start < 0 or end > last_start or start >= end:
            return code
        source = source[:start] + replacement + source[end:]
        last_start = start
    try:
        updated = source.decode('utf-8')
        ast.parse(updated)
        return updated
    except (UnicodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return code


def transform_safe_empty_dict_get_to_none(code: str) -> str:
    """Turn no-default `.get` of an exact empty dict literal into None.

    Only standalone top-level name assignments are eligible. This has no
    dynamic module/name resolution and does not evaluate any nonliteral key.
    """
    parsed = _read(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    edits = []
    for stmt in tree.body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            continue
        expr = stmt.value
        if not (isinstance(expr, ast.Call) and not expr.keywords
                and len(expr.args) == 1
                and isinstance(expr.args[0], ast.Constant)
                and type(expr.args[0].value) in (str, int, bool)
                and isinstance(expr.func, ast.Attribute)
                and expr.func.attr == 'get'
                and isinstance(expr.func.value, ast.Dict)
                and not expr.func.value.keys):
            continue
        start, end = _span(expr, offsets)
        if b'\n' in source[start:end] or b'\r' in source[start:end] or b'#' in source[start:end]:
            continue
        edits.append((start, end, b'None'))
    return _finish(code, source, edits)


def _safe_builtins_binding(tree: ast.Module, stmt: ast.stmt) -> bool:
    imports = [node for node in tree.body
               if isinstance(node, ast.Import)
               for alias in node.names
               if alias.name == 'builtins' and alias.asname is None]
    if len(imports) != 1 or imports[0].lineno >= stmt.lineno:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in ('builtins', 'print') and isinstance(node.ctx, (ast.Store, ast.Del)):
                return False
            if node.id in ('__builtins__', '__dict__'):
                return False
        if isinstance(node, ast.arg) and node.arg in ('builtins', 'print'):
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in ('builtins', 'print'):
            return False
        if isinstance(node, (ast.Global, ast.Nonlocal)) and set(node.names) & {'builtins', 'print'}:
            return False
        if isinstance(node, ast.ExceptHandler) and node.name in ('builtins', 'print'):
            return False
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_DYNAMIC_CALLS:
            return False
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == 'builtins'
                and (not isinstance(node.ctx, ast.Load)
                     or node.attr in ('__dict__', '__setattr__', '__delattr__'))):
            return False
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                binding = alias.asname or alias.name.split('.')[0]
                if alias.name == '*':
                    return False
                if binding in ('builtins', 'print') and not (
                    isinstance(node, ast.Import)
                    and alias.name == 'builtins' and alias.asname is None
                ):
                    return False
    return True


def transform_safe_builtins_print_to_print(code: str) -> str:
    """Simplify direct module-level calls to builtin print, preserving args.

    Rejected on any detectable shadowing, assignment, or dynamic lookup;
    it is still not a proof against opaque runtime monkeypatches.
    """
    parsed = _read(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    edits = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Expr):
            continue
        call = stmt.value
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == 'builtins'
                and call.func.attr == 'print'
                and _safe_builtins_binding(tree, stmt)):
            continue
        start, end = _span(call.func, offsets)
        if source[start:end] != b'builtins.print':
            continue
        edits.append((start, end, b'print'))
    return _finish(code, source, edits)
