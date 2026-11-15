"""Conservative constructor-to-literal conversions for three style tags.

Supported basic / additional / complex examples for each tag are covered by
built-in fixed-fixture tests. This module neither executes user code nor edits
code outside the exact source span of selected constructors. It is a restricted
source transformation, not a proof of arbitrary Python equivalence.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import io
import tokenize

_LITERAL_BUILTINS = frozenset({'list', 'dict', 'tuple'})
_SENSITIVE_NAMES = frozenset({
    'locals', 'globals', 'vars', 'dir', 'eval', 'exec', 'compile',
    'inspect', 'sys', '__import__', 'id',
})
_MAX_LITERAL_ITEMS = 24


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes


def _shadowed(tree: ast.AST, name: str) -> bool:
    """Reject file-wide rebinding rather than making unsound scope guesses."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg == name:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) == name:
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            return True
        if isinstance(node, ast.MatchAs) and node.name == name:
            return True
        if isinstance(node, ast.MatchStar) and node.name == name:
            return True
    return False


def _sensitive(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Is, ast.IsNot)):
            return True
        if isinstance(node, ast.Name) and node.id in _SENSITIVE_NAMES:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name.split('.')[0] in {'inspect', 'sys', 'builtins'}:
                    return True
        if isinstance(node, ast.Attribute) and node.attr in {'__dict__', '__builtins__'}:
            return True
    return False


def _source_literal(node: ast.AST, code: str) -> str | None:
    """Only no-side-effect scalar literals, preserving spelling/escaping."""
    if isinstance(node, ast.Constant) and type(node.value) in (str, bytes, int, float, bool, type(None)):
        return ast.get_source_segment(code, node)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = node.operand
        if isinstance(inner, ast.Constant) and type(inner.value) in (int, float):
            return ast.get_source_segment(code, node)
    return None


def _seq_items(node: ast.AST, code: str) -> list[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple)) or len(node.elts) > _MAX_LITERAL_ITEMS:
        return None
    pieces = [_source_literal(elt, code) for elt in node.elts]
    return pieces if all(part is not None for part in pieces) else None


def _str_items(value: ast.Constant) -> list[str] | None:
    if type(value.value) is str and len(value.value) <= _MAX_LITERAL_ITEMS:
        return [repr(ch) for ch in value.value]
    if type(value.value) is bytes and len(value.value) <= _MAX_LITERAL_ITEMS:
        return [str(ch) for ch in value.value]
    return None


def _render_sequence(node: ast.Call, code: str, kind: str) -> str | None:
    if node.keywords or len(node.args) > 1:
        return None
    if not node.args:
        return '[]' if kind == 'list' else '()'
    arg = node.args[0]
    parts = _seq_items(arg, code)
    if parts is None and isinstance(arg, ast.Constant):
        parts = _str_items(arg)
    if parts is None:
        return None
    if kind == 'list':
        return '[' + ', '.join(parts) + ']'
    # A one-element tuple needs a trailing comma.
    return '(' + ', '.join(parts) + (',' if len(parts) == 1 else '') + ')'


def _render_dict(node: ast.Call, code: str) -> str | None:
    if len(node.args) > 1 or (node.args and node.keywords):
        return None
    pairs: list[tuple[str, str]] = []
    if not node.args:
        if len(node.keywords) > _MAX_LITERAL_ITEMS:
            return None
        for kw in node.keywords:
            if kw.arg is None:
                return None
            value = _source_literal(kw.value, code)
            if value is None:
                return None
            pairs.append((repr(kw.arg), value))
    else:
        source = node.args[0]
        if not isinstance(source, (ast.List, ast.Tuple)) or len(source.elts) > _MAX_LITERAL_ITEMS:
            return None
        for pair in source.elts:
            if not isinstance(pair, (ast.List, ast.Tuple)) or len(pair.elts) != 2:
                return None
            key_node, value_node = pair.elts
            key = _source_literal(key_node, code)
            value = _source_literal(value_node, code)
            if key is None or value is None:
                return None
            # Tuple keys, NaN, and dynamic equality/hash behavior are not handled.
            if isinstance(key_node, ast.Constant):
                valid_key = type(key_node.value) in (str, bytes, int, float, bool, type(None))
            elif isinstance(key_node, ast.UnaryOp) and isinstance(key_node.op, (ast.USub, ast.UAdd)):
                valid_key = (isinstance(key_node.operand, ast.Constant)
                             and type(key_node.operand.value) in (int, float))
            else:
                valid_key = False
            if not valid_key:
                return None
            pairs.append((key, value))
        if len(pairs) != len(source.elts):
            return None
    return '{' + ', '.join(f'{key}: {value}' for key, value in pairs) + '}'


def _render(node: ast.Call, code: str, kind: str) -> str | None:
    if kind in ('list', 'tuple'):
        return _render_sequence(node, code, kind)
    if kind == 'dict':
        return _render_dict(node, code)
    return None


def _offsets(code: str) -> list[int]:
    values = [0]
    for line in code.splitlines(keepends=True):
        values.append(values[-1] + len(line.encode('utf-8')))
    return values


def _edit_for_node(node: ast.Call, value: str, offsets: list[int]) -> _Edit | None:
    if not (node.lineno == node.end_lineno and node.col_offset < node.end_col_offset):
        return None
    if node.lineno >= len(offsets):
        return None
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    return _Edit(start, end, value.encode('utf-8'))


def _rewrite(code: str, kind: str) -> str:
    if not isinstance(code, str):
        return code
    try:
        tree = ast.parse(code)
        if _shadowed(tree, kind) or _sensitive(tree):
            return code
        # A multiline constructor may have comments or continuation trivia.
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
        comments = {token.start[0] for token in tokens if token.type == tokenize.COMMENT}
        offsets = _offsets(code)
        edits: list[_Edit] = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == kind):
                continue
            if any(row in comments for row in range(node.lineno, node.end_lineno + 1)):
                continue
            candidate = _render(node, code, kind)
            if candidate is None:
                continue
            edit = _edit_for_node(node, candidate, offsets)
            if edit is not None:
                edits.append(edit)
        if not edits:
            return code
        # Outermost-first interval selection prevents nested replacements from
        # corrupting byte positions when a user writes nested constructors.
        edits.sort(key=lambda e: (e.start, -e.end))
        selected: list[_Edit] = []
        last_end = -1
        for edit in edits:
            if edit.start >= last_end:
                selected.append(edit)
                last_end = edit.end
        raw = code.encode('utf-8')
        for edit in reversed(selected):
            raw = raw[:edit.start] + edit.replacement + raw[edit.end:]
        result = raw.decode('utf-8')
        ast.parse(result)
        return result
    except (SyntaxError, ValueError, IndentationError, tokenize.TokenError, UnicodeError):
        return code


def transform_to_list_literal(code: str) -> str:
    return _rewrite(code, 'list')


def transform_to_dict_literal(code: str) -> str:
    return _rewrite(code, 'dict')


def transform_to_tuple_literal(code: str) -> str:
    return _rewrite(code, 'tuple')
