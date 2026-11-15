"""Conservative, source-preserving transforms for observed style preferences.

The two transforms act only on a statically proven, adjacent pair of Python
statements. No submitted source is executed. Unsupported cases remain unchanged.
This is not a proof of equivalence for all Python programs.
"""
from __future__ import annotations

import ast
import io
import tokenize

MAX_EDITS = 24
DYNAMIC_NAMES = frozenset({
    'eval', 'exec', 'locals', 'globals', 'vars', 'dir', 'compile',
    'inspect', 'sys', 'traceback', '__import__', '__builtins__',
    'builtins', 'setattr', 'getattr', 'delattr',
})


def _parsed(source: str) -> ast.Module | None:
    if not isinstance(source, str):
        return None
    try:
        return ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return None


def _comment_lines(source: str) -> set[int] | None:
    try:
        return {t.start[0] for t in tokenize.generate_tokens(io.StringIO(source).readline)
                if t.type == tokenize.COMMENT}
    except (IndentationError, tokenize.TokenError):
        return None


def _is_dynamic(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.NamedExpr)):
            return True
        if isinstance(node, ast.Name) and node.id in DYNAMIC_NAMES:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] in DYNAMIC_NAMES:
                return True
            if any(alias.name.split('.')[0] in DYNAMIC_NAMES
                   or (alias.asname or '') in DYNAMIC_NAMES for alias in node.names):
                return True
    return False


def _blocks(tree: ast.AST):
    for parent in ast.walk(tree):
        for _, sequence in ast.iter_fields(parent):
            if (isinstance(sequence, list) and len(sequence) > 1
                    and all(isinstance(s, ast.stmt) for s in sequence)):
                # Avoid editing async/generator contexts while evaluating safety.
                if isinstance(parent, (ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                for left, right in zip(sequence, sequence[1:]):
                    yield left, right


def _offsets(source: str) -> list[int]:
    result = [0]
    for line in source.splitlines(keepends=True):
        result.append(result[-1] + len(line.encode('utf-8')))
    return result


def _span(node: ast.AST, offsets: list[int]) -> tuple[int, int] | None:
    line, end_line = getattr(node, 'lineno', None), getattr(node, 'end_lineno', None)
    col, end_col = getattr(node, 'col_offset', None), getattr(node, 'end_col_offset', None)
    if (type(line) is not int or type(end_line) is not int
            or type(col) is not int or type(end_col) is not int
            or not 1 <= line == end_line < len(offsets)):
        return None
    return offsets[line - 1] + col, offsets[end_line - 1] + end_col


def _edit(source: str, edits: list[tuple[int, int, str]]) -> str:
    data = source.encode('utf-8')
    end_of_previous = -1
    for first, last, _ in sorted(edits):
        if first < end_of_previous or last <= first:
            return source
        end_of_previous = last
    for first, last, replacement in sorted(edits, reverse=True):
        data = data[:first] + replacement.encode('utf-8') + data[last:]
    try:
        changed = data.decode('utf-8')
    except UnicodeDecodeError:
        return source
    return changed if _parsed(changed) is not None else source


def _int_value(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _int_value(node.operand)
        return (-v if isinstance(node.op, ast.USub) else v) if v is not None else None
    return None


def transform_to_augmented_assignment(source: str) -> str:
    """Basic: int +; additional: int -/*; compound: within function/branches.

    Only `n = integer_literal` immediately followed by `n = n <op> integer`
    is changed. The prior integer binding proves ordinary int inplace math.
    All other references and comments are preserved verbatim.
    """
    tree = _parsed(source)
    comments = _comment_lines(source) if tree is not None else None
    if tree is None or comments is None or _is_dynamic(tree):
        return source
    offsets = _offsets(source)
    edits: list[tuple[int, int, str]] = []
    for left, right in _blocks(tree):
        if not (isinstance(left, ast.Assign) and isinstance(right, ast.Assign)
                and len(left.targets) == len(right.targets) == 1
                and isinstance(left.targets[0], ast.Name)
                and isinstance(right.targets[0], ast.Name)
                and left.targets[0].id == right.targets[0].id
                and _int_value(left.value) is not None
                and left.end_lineno is not None and left.end_lineno + 1 == right.lineno
                and isinstance(right.value, ast.BinOp)):
            continue
        name = right.targets[0].id
        expr = right.value
        if not (isinstance(expr.left, ast.Name) and expr.left.id == name
                and isinstance(expr.op, (ast.Add, ast.Sub, ast.Mult))
                and _int_value(expr.right) is not None):
            continue
        if (left.lineno in comments or right.lineno in comments
                or left.lineno != left.end_lineno or right.lineno != right.end_lineno):
            continue
        span = _span(right, offsets)
        value_text = ast.get_source_segment(source, expr.right)
        if span is None or not value_text or '\n' in value_text or '\r' in value_text:
            continue
        symbol = '+' if isinstance(expr.op, ast.Add) else '-' if isinstance(expr.op, ast.Sub) else '*'
        edits.append((*span, f'{name} {symbol}= {value_text}'))
        if len(edits) >= MAX_EDITS:
            break
    return _edit(source, edits) if edits else source


def _literal_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return type(node.value) in (str, int, bool, float, type(None))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return (isinstance(node.operand, ast.Constant)
                and type(node.operand.value) in (int, float))
    return False


def _dict_has_static_key(dictionary: ast.Dict, key: ast.AST) -> bool:
    if len(dictionary.keys) > 30 or not _literal_constant(key):
        return False
    if any(k is None or not _literal_constant(k) or not _literal_constant(v)
           for k, v in zip(dictionary.keys, dictionary.values)):
        return False
    try:
        entries = ast.literal_eval(dictionary)
        requested_key = ast.literal_eval(key)
        return type(entries) is dict and requested_key in entries
    except (TypeError, ValueError, SyntaxError, OverflowError):
        return False


def _lookup_subscript(stmt: ast.stmt) -> ast.Subscript | None:
    # Restrict the lookup to a single, last operation in a statement, so no
    # intervening function call can replace or mutate the literal dict.
    if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)):
        candidate = stmt.value
    elif isinstance(stmt, ast.Return):
        candidate = stmt.value
    elif (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
          and isinstance(stmt.value.func, ast.Name)
          and stmt.value.func.id == 'print' and len(stmt.value.args) == 1
          and not stmt.value.keywords):
        candidate = stmt.value.args[0]
    else:
        return None
    return candidate if isinstance(candidate, ast.Subscript) else None


def transform_to_dict_get(source: str) -> str:
    """Basic: string key; additional: integer key; complex: return/print scope.

    Only literal dicts followed immediately by a known-key lookup are edited.
    A dynamic dict or missing key is never rewritten (KeyError != None).
    """
    tree = _parsed(source)
    comments = _comment_lines(source) if tree is not None else None
    if tree is None or comments is None or _is_dynamic(tree):
        return source
    offsets = _offsets(source)
    edits: list[tuple[int, int, str]] = []
    for left, right in _blocks(tree):
        if not (isinstance(left, ast.Assign) and len(left.targets) == 1
                and isinstance(left.targets[0], ast.Name)
                and isinstance(left.value, ast.Dict)
                and left.end_lineno is not None and left.end_lineno + 1 == right.lineno
                and left.lineno == left.end_lineno and right.lineno == right.end_lineno):
            continue
        subscript = _lookup_subscript(right)
        if not (subscript is not None and isinstance(subscript.value, ast.Name)
                and subscript.value.id == left.targets[0].id
                and _dict_has_static_key(left.value, subscript.slice)):
            continue
        if left.lineno in comments or right.lineno in comments:
            continue
        span = _span(subscript, offsets)
        key = ast.get_source_segment(source, subscript.slice)
        if span is None or not key or '\n' in key or '\r' in key:
            continue
        edits.append((*span, f'{subscript.value.id}.get({key})'))
        if len(edits) >= MAX_EDITS:
            break
    return _edit(source, edits) if edits else source
