"""Batch29: equivalent surface forms for explicitly/implicitly defaulted calls.

Only direct, module-level assignments of pure builtin literal expressions are
rewritten. The restrictive grammar avoids arbitrary code evaluation or callable
name shadowing. Successful AST tests alone are not universal equivalence proofs.
"""
from __future__ import annotations

import ast

MAX_CHARS = 250_000
_DYNAMIC = frozenset({'exec', 'eval', 'globals', 'locals', 'vars', 'compile',
                     '__import__', 'setattr', 'delattr'})


def _parse(code):
    if not isinstance(code, str) or not code or len(code) > MAX_CHARS:
        return None
    try:
        tree = ast.parse(code)
        source = code.encode('utf-8')
        offsets = [0]
        for line in code.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line.encode('utf-8')))
        return tree, source, offsets
    except (SyntaxError, UnicodeError, ValueError, RecursionError, MemoryError):
        return None


def _span(node, offsets):
    return (offsets[node.lineno - 1] + node.col_offset,
            offsets[node.end_lineno - 1] + node.end_col_offset)


def _replace(code, source, edits):
    if not edits:
        return code
    end_last = len(source) + 1
    for start, end, replacement in sorted(edits, reverse=True):
        if not (0 <= start < end <= end_last):
            return code
        source = source[:start] + replacement + source[end:]
        end_last = start
    try:
        result = source.decode('utf-8')
        ast.parse(result)
        return result
    except (UnicodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return code


def _safe_module(tree, protect_sorted):
    for node in ast.walk(tree):
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            # Reject import hooks and namespace changes in these tiny fixtures.
            return False
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.NamedExpr)):
            return False
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _DYNAMIC:
                return False
        if isinstance(node, ast.Name) and protect_sorted:
            if node.id == 'sorted' and not isinstance(node.ctx, ast.Load):
                return False
            if node.id in {'__builtins__', '__dict__'}:
                return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.Lambda, ast.Delete, ast.Starred)):
            return False
    return True


def _literal_list(node):
    if not isinstance(node, ast.List) or not node.elts or len(node.elts) > 40:
        return False
    types = set()
    for item in node.elts:
        if not isinstance(item, ast.Constant) or type(item.value) not in (int, str, float):
            return False
        types.add(type(item.value))
    return len(types) == 1


def _assignment_calls(tree):
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Call)):
            yield stmt.value


def _sorted_default(code, explicit):
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    if not _safe_module(tree, True):
        return code
    edits = []
    for call in _assignment_calls(tree):
        if not (isinstance(call.func, ast.Name) and call.func.id == 'sorted'
                and len(call.args) == 1 and _literal_list(call.args[0])):
            continue
        start, end = _span(call, offsets)
        actual = source[start:end]
        a_start, a_end = _span(call.args[0], offsets)
        arg = source[a_start:a_end]
        if b'\n' in actual or b'\r' in actual or b'#' in actual or b'\\' in actual:
            continue
        implicit = b'sorted(' + arg + b')'
        specified = b'sorted(' + arg + b', reverse=False)'
        if explicit and not call.keywords and actual == implicit:
            edits.append((start, end, specified))
        elif (not explicit and len(call.keywords) == 1
              and call.keywords[0].arg == 'reverse'
              and isinstance(call.keywords[0].value, ast.Constant)
              and call.keywords[0].value.value is False and actual == specified):
            edits.append((start, end, implicit))
    return _replace(code, source, edits)


def _strip_default(code, explicit):
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    if not _safe_module(tree, False):
        return code
    edits = []
    for call in _assignment_calls(tree):
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == 'strip'
                and isinstance(func.value, ast.Constant)
                and type(func.value.value) is str and not call.keywords):
            continue
        start, end = _span(call, offsets)
        a_start, a_end = _span(func.value, offsets)
        obj = source[a_start:a_end]
        actual = source[start:end]
        if b'\n' in actual or b'\r' in actual or b'#' in actual or b'\\' in actual:
            continue
        implicit = obj + b'.strip()'
        specified = obj + b'.strip(None)'
        if explicit and not call.args and actual == implicit:
            edits.append((start, end, specified))
        elif (not explicit and len(call.args) == 1
              and isinstance(call.args[0], ast.Constant)
              and call.args[0].value is None and actual == specified):
            edits.append((start, end, implicit))
    return _replace(code, source, edits)


def transform_sorted_explicit_reverse_default(code):
    return _sorted_default(code, True)


def transform_sorted_implicit_reverse_default(code):
    return _sorted_default(code, False)


def transform_strip_explicit_none_default(code):
    return _strip_default(code, True)


def transform_strip_implicit_none_default(code):
    return _strip_default(code, False)
