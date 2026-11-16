"""Batch 21: narrowly scoped, style-directed Python edits.

1) Top-level ``builtins.input(...)`` -> ``input(...)`` only with a unique
   prior direct import and no detectable name shadowing or dynamic mutation.
2) ``if __debug__: if not NAME: raise AssertionError(MESSAGE)`` ->
   ``assert NAME, MESSAGE`` (or assert NAME without a message).
   The explicit __debug__ guard is required so both versions are skipped
   under python -O. The original assertion class must not be shadowed.

These are source-level rewrites. Exact equivalence for arbitrary dynamically
mutated programs cannot be proved; the runtime verifier remains authoritative.
"""
from __future__ import annotations

import ast

MAX_CHARS = 250_000
_DYNAMIC_NAMES = frozenset({'globals', 'locals', 'vars', 'exec', 'eval',
                            '__import__', 'setattr', 'delattr', 'compile'})


def _parse(code: str):
    if not isinstance(code, str) or not code or len(code) > MAX_CHARS:
        return None
    try:
        tree = ast.parse(code)
        source = code.encode('utf-8')
        offsets = [0]
        for line in code.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line.encode('utf-8')))
        return tree, source, offsets
    except (SyntaxError, TypeError, ValueError, UnicodeError,
            RecursionError, MemoryError):
        return None


def _span(node, offsets):
    return (offsets[node.lineno - 1] + node.col_offset,
            offsets[node.end_lineno - 1] + node.end_col_offset)


def _apply(code, source, edits):
    if not edits:
        return code
    cursor = len(source) + 1
    for start, end, replacement in sorted(edits, reverse=True):
        if not 0 <= start < end <= cursor:
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


def _binding_safe(tree: ast.Module, protected: set[str]) -> bool:
    """Reject lexical rebinding and obvious namespace/builtins mutation."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in protected and isinstance(node.ctx, (ast.Store, ast.Del)):
                return False
            if node.id in {'__builtins__', '__dict__'}:
                return False
        if isinstance(node, ast.arg) and node.arg in protected:
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in protected:
            return False
        if isinstance(node, (ast.Global, ast.Nonlocal)) and set(node.names) & protected:
            return False
        if isinstance(node, ast.ExceptHandler) and node.name in protected:
            return False
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _DYNAMIC_NAMES:
            return False
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == '*' for alias in node.names):
                return False
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split('.')[0]
                if bound in protected:
                    if not (isinstance(node, ast.Import) and alias.name == 'builtins'
                            and alias.asname is None and bound == 'builtins'):
                        return False
        # Modifications through the module object can change resolution.
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == 'builtins' and (
                not isinstance(node.ctx, ast.Load)
                or node.attr in ('__dict__', '__setattr__', '__delattr__')
            ):
                return False
    return True


def transform_safe_builtin_input(code: str) -> str:
    """Simplify prior-imported builtins.input at a top-level assignment/call.

    Only the function name changes. The input arguments, prompts and stdin
    consumption stay unchanged. Nested/overridden names are excluded.
    """
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    imports = [stmt for stmt in tree.body if isinstance(stmt, ast.Import)
               for alias in stmt.names if alias.name == 'builtins' and alias.asname is None]
    if len(imports) != 1 or not _binding_safe(tree, {'input', 'builtins'}):
        return code
    edits = []
    for stmt in tree.body:
        if not isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign)):
            continue
        if isinstance(stmt, ast.Assign) and (
            len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name)
        ):
            continue
        if isinstance(stmt, ast.AnnAssign) and not isinstance(stmt.target, ast.Name):
            continue
        call = stmt.value
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == 'builtins'
                and call.func.attr == 'input'
                and imports[0].lineno < stmt.lineno):
            continue
        start, end = _span(call.func, offsets)
        if source[start:end] == b'builtins.input':
            edits.append((start, end, b'input'))
    return _apply(code, source, edits)


def transform_debug_guard_to_assert(code: str) -> str:
    """Collapse an explicit __debug__ / AssertionError guard to assert.

    The guarded condition must be a single name. An optional diagnostic must
    be a primitive literal. Since __debug__ is compile-time constant, both
    forms are removed by -O. No arbitrary evaluation is added.
    """
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    if not _binding_safe(tree, {'AssertionError'}):
        return code
    edits = []
    for outer in ast.walk(tree):
        if not (isinstance(outer, ast.If) and not outer.orelse
                and isinstance(outer.test, ast.Name) and outer.test.id == '__debug__'
                and len(outer.body) == 1):
            continue
        inner = outer.body[0]
        if not (isinstance(inner, ast.If) and not inner.orelse
                and len(inner.body) == 1 and
                isinstance(inner.test, ast.UnaryOp) and isinstance(inner.test.op, ast.Not)
                and isinstance(inner.test.operand, ast.Name)):
            continue
        raise_stmt = inner.body[0]
        if not isinstance(raise_stmt, ast.Raise) or raise_stmt.cause is not None:
            continue
        exc = raise_stmt.exc
        msg = None
        if isinstance(exc, ast.Name) and exc.id == 'AssertionError':
            pass
        elif (isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
              and exc.func.id == 'AssertionError' and not exc.keywords
              and len(exc.args) <= 1):
            if exc.args:
                msg = exc.args[0]
                if not (isinstance(msg, ast.Constant)
                        and type(msg.value) in (str, int, float, bool, type(None))):
                    continue
        else:
            continue
        start, end = _span(outer, offsets)
        original_span = source[start:end]
        # Preserve comments and nonstandard multiline literals untouched.
        if b'#' in original_span or b'\\' in original_span:
            continue
        ns, ne = _span(inner.test.operand, offsets)
        condition = source[ns:ne]
        # only a simple (ASCII/Unicode) identifier: avoid a multiline expr
        if condition.decode('utf-8') != inner.test.operand.id:
            continue
        replacement = b'assert ' + condition
        if msg is not None:
            ms, me = _span(msg, offsets)
            literal = source[ms:me]
            if b'\n' in literal or b'\r' in literal:
                continue
            replacement += b', ' + literal
        edits.append((start, end, replacement))
    # AST.walk can include nested candidates. They cannot overlap in the
    # accepted exact shape, but fail closed if they somehow do.
    edits.sort()
    if any(edits[i][1] > edits[i + 1][0] for i in range(len(edits) - 1)):
        return code
    return _apply(code, source, edits)
