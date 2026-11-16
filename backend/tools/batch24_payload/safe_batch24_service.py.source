"""Batch 24: highly constrained import and output-style transformations.

The precondition intentionally accepts only a top-level series of literal
assignments and builtin print calls. No user-supplied Python is evaluated.

1. import style: print(...) -> import builtins; builtins.print(...)
2. I/O style: print('a', 'b') -> print('a b')

These are observationally equivalent under normal Python builtins, not a proof
for tracing, externally monkeypatched builtins, or reflective code.
"""
from __future__ import annotations

import ast

MAX_CHARS = 250_000
_LITERAL_TYPES = (str, int, float, bool, type(None))


def _parse_simple_module(code: str):
    if not isinstance(code, str) or not code or len(code) > MAX_CHARS:
        return None
    # A new import ahead of a shebang, PEP 263 encoding line or comments could
    # change module conventions. Decline to transform these inputs.
    if not code or code[0] in '#\n\r\ufeff' or code.startswith((' ', '\t')):
        return None
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, TypeError, UnicodeError, RecursionError, MemoryError):
        return None
    if not tree.body:
        return None
    print_calls = []
    declared = set()
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            if (len(statement.targets) != 1
                    or not isinstance(statement.targets[0], ast.Name)
                    or statement.targets[0].id in {'print', 'builtins', '__builtins__'}
                    or not isinstance(statement.value, ast.Constant)
                    or type(statement.value.value) not in _LITERAL_TYPES):
                return None
            declared.add(statement.targets[0].id)
        elif isinstance(statement, ast.Expr):
            call = statement.value
            if (not isinstance(call, ast.Call)
                    or not isinstance(call.func, ast.Name)
                    or call.func.id != 'print'
                    or call.keywords
                    or len(call.args) == 0 or len(call.args) > 5
                    or not all(isinstance(arg, (ast.Name, ast.Constant))
                               for arg in call.args)):
                return None
            # Do not permit print(print), print(a.b), print(a+b), starred args,
            # or other expressions with side effects.
            for arg in call.args:
                if isinstance(arg, ast.Name):
                    if arg.id not in declared:
                        return None
                elif type(arg.value) not in _LITERAL_TYPES:
                    return None
            if call.lineno != call.end_lineno:
                return None
            print_calls.append(call)
        else:
            # Rebinds, def/import, decorators, exceptions and control flow
            # are intentionally outside this narrow family.
            return None
    if not print_calls:
        return None
    raw = code.encode('utf-8')
    offsets = [0]
    for line in code.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    return tree, print_calls, raw, offsets


def _span(node, offsets):
    return offsets[node.lineno - 1] + node.col_offset, offsets[node.end_lineno - 1] + node.end_col_offset


def _apply_edits(code, raw, edits):
    if not edits:
        return code
    last = len(raw) + 1
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        if not (0 <= start < end <= last):
            return code
        raw = raw[:start] + replacement + raw[end:]
        last = start
    try:
        updated = raw.decode('utf-8')
        ast.parse(updated)
        return updated
    except (SyntaxError, UnicodeError, ValueError, RecursionError, MemoryError):
        return code


def transform_simple_print_to_explicit_builtins_import(code: str) -> str:
    """Add an explicit builtins import for a simple print-only module."""
    parsed = _parse_simple_module(code)
    if parsed is None:
        return code
    _, calls, raw, offsets = parsed
    edits = []
    for call in calls:
        start, end = _span(call.func, offsets)
        if raw[start:end] != b'print':
            return code
        edits.append((start, end, b'builtins.print'))
    updated = _apply_edits(code, raw, edits)
    if updated == code:
        return code
    eol = '\r\n' if '\r\n' in code and '\n' not in code.replace('\r\n', '') else '\n'
    result = 'import builtins' + eol + updated
    try:
        ast.parse(result)
        return result
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return code


def transform_simple_literal_print_arguments(code: str) -> str:
    """Collapse constant string print arguments while preserving stdout."""
    parsed = _parse_simple_module(code)
    if parsed is None:
        return code
    _, calls, raw, offsets = parsed
    edits = []
    for call in calls:
        if len(call.args) < 2:
            continue
        if not all(isinstance(arg, ast.Constant) and type(arg.value) is str
                   for arg in call.args):
            continue
        start, _ = _span(call.args[0], offsets)
        _, end = _span(call.args[-1], offsets)
        if b'#' in raw[start:end] or b'\r' in raw[start:end] or b'\n' in raw[start:end]:
            continue
        replacement = repr(' '.join(arg.value for arg in call.args)).encode('utf-8')
        edits.append((start, end, replacement))
    return _apply_edits(code, raw, edits)
