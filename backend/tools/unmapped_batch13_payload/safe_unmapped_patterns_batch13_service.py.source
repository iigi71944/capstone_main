"""Batch 13: conservative builtin-constructor calls -> equivalent literals.

Only these builtin forms are rewritten:
  str(), str(None/True/False) -> exact string literal
  int(), int(True/False)      -> integer literal
  bool(), bool(None/0/1)      -> boolean literal

No user code is executed. Static AST checks reject imports, dynamic global
mutation/introspection, and any binding of the relevant builtin names. Byte
edits preserve unrelated comments, whitespace, and LF/CRLF exactly.
Examples are not a universal program-equivalence proof.
"""
from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes


_TARGETS = frozenset({'str', 'int', 'bool'})
_DYNAMIC_NAMES = frozenset({
    '__builtins__', 'builtins', 'globals', 'locals', 'vars', 'exec', 'eval',
    'compile', '__import__', 'setattr', 'delattr', 'getattr',
})


def _safe_module(tree: ast.AST) -> bool:
    """Fail closed on shadowing and dynamic builtin replacement patterns."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False
        if isinstance(node, ast.Name):
            if node.id in _DYNAMIC_NAMES:
                return False
            if node.id in _TARGETS and isinstance(node.ctx, (ast.Store, ast.Del)):
                return False
        if isinstance(node, ast.arg) and node.arg in _TARGETS:
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in _TARGETS:
                return False
        if isinstance(node, ast.ExceptHandler) and node.name in _TARGETS:
            return False
        if isinstance(node, (ast.Global, ast.Nonlocal)) and _TARGETS.intersection(node.names):
            return False
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name in _TARGETS:
            return False
        if isinstance(node, ast.MatchMapping) and node.rest in _TARGETS:
            return False
        if isinstance(node, ast.Attribute) and node.attr == '__builtins__':
            return False
    return True


def _literal_for_call(call: ast.Call) -> str | None:
    if not (isinstance(call.func, ast.Name)
            and call.func.id in _TARGETS
            and not call.keywords and len(call.args) <= 1):
        return None
    name = call.func.id
    if not call.args:
        return {'str': "''", 'int': '0', 'bool': 'False'}[name]
    arg = call.args[0]
    if not isinstance(arg, ast.Constant):
        return None
    value = arg.value
    if name == 'str':
        if value is None:
            return "'None'"
        if type(value) is bool:
            return "'True'" if value else "'False'"
    if name == 'int' and type(value) is bool:
        return '1' if value else '0'
    if name == 'bool':
        if value is None:
            return 'False'
        if type(value) is int and value in (0, 1):
            return 'True' if value else 'False'
    return None


def _source_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    return offsets


def _comment_spans(source: str, offsets: list[int]) -> list[tuple[int, int]]:
    lines = source.splitlines(keepends=True)
    spans = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            line, col = token.start
            end_line, end_col = token.end
            start = offsets[line - 1] + len(lines[line - 1][:col].encode('utf-8'))
            end = offsets[end_line - 1] + len(lines[end_line - 1][:end_col].encode('utf-8'))
            spans.append((start, end))
    return spans


def _rewrite(source: str, builtin: str) -> str:
    try:
        tree = ast.parse(source)
        if not _safe_module(tree):
            return source
        offsets = _source_offsets(source)
        comments = _comment_spans(source, offsets)
        edits: list[_Edit] = []
        data = source.encode('utf-8')
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == builtin):
                continue
            replacement = _literal_for_call(node)
            if replacement is None:
                continue
            start = offsets[node.lineno - 1] + node.col_offset
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            if not (0 <= start < end <= len(data)):
                return source
            if any(cstart < end and start < cend for cstart, cend in comments):
                continue
            edits.append(_Edit(start, end, replacement.encode('utf-8')))
        if not edits:
            return source
        ordered = sorted(edits, key=lambda e: e.start)
        if any(previous.end > current.start for previous, current in zip(ordered, ordered[1:])):
            return source
        for edit in reversed(ordered):
            data = data[:edit.start] + edit.replacement + data[edit.end:]
        changed = data.decode('utf-8')
        ast.parse(changed)
        return changed
    except (SyntaxError, ValueError, UnicodeError, tokenize.TokenError, IndexError, TypeError):
        return source


def transform_to_safe_string_literal_style(source: str) -> str:
    return _rewrite(source, 'str')


def transform_to_safe_number_literal_style(source: str) -> str:
    return _rewrite(source, 'int')


def transform_to_safe_boolean_literal_style(source: str) -> str:
    return _rewrite(source, 'bool')
