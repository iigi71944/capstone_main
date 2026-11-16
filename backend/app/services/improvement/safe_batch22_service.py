"""Batch 22: constrained, style-directed AST/source-span rewrites.

1. Expand a top-level unpacking assignment of *primitive literal values* into
   sequential simple assignments. Reject side effects, comments in the span,
   and statement chaining.
2. Expand ``if __debug__: assert flag, 'error'`` into a guarded explicit
   ``if not flag: raise AssertionError('error')``. This preserves optimized
   execution (-O) and expression evaluation under the specified conditions.

These are narrow patterns, not proofs of arbitrary-program equivalence.
"""
from __future__ import annotations

import ast

MAX_CHARS = 250_000
_DYNAMIC = frozenset({'globals', 'locals', 'vars', 'exec', 'eval',
                      '__import__', 'setattr', 'delattr', 'compile'})
_LITERAL_TYPES = (int, float, bool, str, type(None))


def _parse(code: str):
    if not isinstance(code, str) or not code or len(code) > MAX_CHARS:
        return None
    try:
        tree = ast.parse(code)
        data = code.encode('utf-8')
        offsets = [0]
        for line in code.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line.encode('utf-8')))
        return tree, data, offsets, code.splitlines(keepends=True)
    except (SyntaxError, UnicodeError, ValueError, TypeError,
            RecursionError, MemoryError):
        return None


def _span(node: ast.AST, offsets: list[int]) -> tuple[int, int]:
    return (offsets[node.lineno - 1] + node.col_offset,
            offsets[node.end_lineno - 1] + node.end_col_offset)


def _finish(code: str, source: bytes, edits):
    if not edits:
        return code
    cursor = len(source) + 1
    for start, end, replacement in sorted(edits, reverse=True):
        if not (0 <= start < end <= cursor):
            return code
        source = source[:start] + replacement + source[end:]
        cursor = start
    try:
        output = source.decode('utf-8')
        ast.parse(output)
        return output
    except (SyntaxError, ValueError, UnicodeError,
            RecursionError, MemoryError):
        return code


def _primitive(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) in _LITERAL_TYPES


def transform_literal_unpack_to_assignments(code: str) -> str:
    """Expand ``left, right = (1, 2)`` at module scope only.

    The entire right-hand expression must be literal, and each target must be
    a distinct unqualified identifier. No intermediate evaluation side effect.
    """
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets, lines = parsed
    eol = b'\r\n' if b'\r\n' in source else b'\n'
    edits = []
    for stmt in tree.body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Tuple)
                and isinstance(stmt.value, ast.Tuple)):
            continue
        names = stmt.targets[0].elts
        vals = stmt.value.elts
        if (not 2 <= len(names) == len(vals) <= 8
                or not all(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                           and not n.id.startswith('__') for n in names)
                or len({n.id for n in names}) != len(names)
                or not all(_primitive(v) for v in vals)):
            continue
        start, end = _span(stmt, offsets)
        original = source[start:end]
        if any(ch in original for ch in (b'\n', b'\r', b'#', b';', b'\\')):
            continue
        # No semicolon/chained statement after assignment on this line.
        suffix = lines[stmt.end_lineno - 1].encode('utf-8')[stmt.end_col_offset:]
        if suffix.split(b'#', 1)[0].strip():
            continue
        pieces = []
        for target, value in zip(names, vals):
            lo, hi = _span(value, offsets)
            literal = source[lo:hi]
            if not literal or b'\n' in literal or b'\r' in literal:
                break
            pieces.append(target.id.encode('utf-8') + b' = ' + literal)
        else:
            edits.append((start, end, eol.join(pieces)))
    return _finish(code, source, edits)


def _error_binding_safe(tree: ast.AST) -> bool:
    protected = {'AssertionError', '__builtins__'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id == '__builtins__':
                return False
            if node.id == 'AssertionError' and isinstance(node.ctx, (ast.Store, ast.Del)):
                return False
        if isinstance(node, ast.arg) and node.arg in protected:
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in protected:
            return False
        if isinstance(node, (ast.Global, ast.Nonlocal)) and set(node.names) & protected:
            return False
        if isinstance(node, ast.ExceptHandler) and node.name in protected:
            return False
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _DYNAMIC:
            return False
        if isinstance(node, ast.ImportFrom) and any(a.name == '*' for a in node.names):
            return False
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.asname or alias.name.split('.')[0]) in protected:
                    return False
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == 'builtins' and (
                node.attr in ('AssertionError', '__dict__', '__setattr__', '__delattr__')
                and (not isinstance(node.ctx, ast.Load) or node.attr != 'AssertionError')
            ):
                return False
    return True


def transform_debug_assert_to_raise(code: str) -> str:
    """Expand a debug-guarded `assert NAME[, CONSTANT]` conservatively.

    Keep the outer __debug__ check, matching python -O behavior. Reject any
    detectable AssertionError rebinding and comments in the rewritten span.
    """
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets, lines = parsed
    if not _error_binding_safe(tree):
        return code
    eol = b'\r\n' if b'\r\n' in source else b'\n'
    edits = []
    for outer in ast.walk(tree):
        if not (isinstance(outer, ast.If) and not outer.orelse
                and isinstance(outer.test, ast.Name)
                and outer.test.id == '__debug__' and len(outer.body) == 1):
            continue
        stmt = outer.body[0]
        if not (isinstance(stmt, ast.Assert)
                and isinstance(stmt.test, ast.Name)
                and (stmt.msg is None or _primitive(stmt.msg))):
            continue
        start, end = _span(outer, offsets)
        original = source[start:end]
        if any(ch in original for ch in (b'#', b'\\')):
            continue
        # Restrict to space-indented exact syntax; source preservation matters.
        first = lines[outer.lineno - 1].encode('utf-8')
        if first[:outer.col_offset] != b' ' * outer.col_offset:
            continue
        if b';' in original:
            continue
        # No extra statements on the final line.
        suffix = lines[outer.end_lineno - 1].encode('utf-8')[outer.end_col_offset:]
        if suffix.split(b'#', 1)[0].strip():
            continue
        name = stmt.test.id.encode('utf-8')
        if stmt.msg is None:
            exc = b'raise AssertionError'
        else:
            ms, me = _span(stmt.msg, offsets)
            msg = source[ms:me]
            if not msg or b'\n' in msg or b'\r' in msg:
                continue
            exc = b'raise AssertionError(' + msg + b')'
        indent = b' ' * outer.col_offset
        replacement = (b'if __debug__:' + eol + indent + b'    if not ' + name + b':'
                       + eol + indent + b'        ' + exc)
        edits.append((start, end, replacement))
    if any(a[1] > b[0] for a, b in zip(sorted(edits), sorted(edits)[1:])):
        return code
    return _finish(code, source, edits)
