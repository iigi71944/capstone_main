"""Conservative source-preserving dict.get -> known-key indexing.

The rewrite only operates on an immediately preceding literal dictionary
binding with a statically present immutable scalar key.  It never executes
user code and intentionally declines ambiguous scopes, mutation, introspection
and comments inside the edited expression. This is *not* a general semantic
preservation theorem for arbitrary Python.
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
import io
import tokenize


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    text: bytes


_SENSITIVE_NAMES = frozenset({
    'locals', 'globals', 'vars', 'dir', 'eval', 'exec', '__import__',
    'inspect', 'sys', 'builtins', 'setattr', 'delattr', 'compile',
})


def _key(node: ast.AST) -> object | None:
    if isinstance(node, ast.Constant) and type(node.value) in (str, int):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub))
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) is int):
        return (+node.operand.value if isinstance(node.op, ast.UAdd)
                else -node.operand.value)
    return None


def _has_sensitive_use(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _SENSITIVE_NAMES:
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if any(alias.name.split('.')[0] in {'inspect', 'sys', 'builtins'}
                   for alias in node.names):
                return True
        if isinstance(node, ast.Attribute) and node.attr in {
            '__class__', '__dict__', '__getattribute__', '__getattr__',
        }:
            return True
    return False


def _line_offsets(code: str) -> list[int]:
    offsets = [0]
    for line in code.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    return offsets


def _literal_dict(statement: ast.stmt) -> tuple[str, dict[object, ast.AST]] | None:
    if not (isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Dict)):
        return None
    value = statement.value
    if len(value.keys) > 24 or not value.keys:
        return None
    mapping: dict[object, ast.AST] = {}
    for key_node, val_node in zip(value.keys, value.values):
        if key_node is None or (key := _key(key_node)) is None:
            return None
        # Omit dynamic value expressions, since they can mutate globals or
        # return unexpected dictionary subclasses on a strange code path.
        if not (isinstance(val_node, ast.Constant)
                and type(val_node.value) in (str, int, float, bool, type(None))):
            return None
        mapping[key] = key_node
    return statement.targets[0].id, mapping


def _eligible_lookup(node: ast.AST, name: str, mapping: dict) -> bool:
    if not (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == name
            and node.func.attr == 'get'
            and len(node.args) == 1 and not node.keywords):
        return False
    value = _key(node.args[0])
    return value is not None and value in mapping


def _comment_tokens(code: str) -> tuple[Counter[str], list[tokenize.TokenInfo]]:
    tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    return Counter(t.string for t in tokens if t.type == tokenize.COMMENT), tokens


def _parent_statement_lists(tree: ast.AST):
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                               ast.Module, ast.If, ast.For, ast.While, ast.With,
                               ast.AsyncWith, ast.Try, ast.ExceptHandler, ast.Match)):
            for _, block in ast.iter_fields(parent):
                if (isinstance(block, list) and len(block) >= 2
                        and all(isinstance(s, ast.stmt) for s in block)):
                    yield block


def transform_to_known_key_indexing(code: str) -> str:
    """Translate literal_dict.get(existing_constant_key) to literal_dict[key].

    Targets must occur in the single following statement in the same block.
    A scope-level variable rebind, introspection, method monkey-patch, or
    inline comment inside the exact replaced call makes that site ineligible.
    """
    try:
        tree = ast.parse(code)
        if _has_sensitive_use(tree):
            return code
        before_comments, tokens = _comment_tokens(code)
        offsets = _line_offsets(code)
        edits: list[_Edit] = []
        for block in _parent_statement_lists(tree):
            for prev, next_stmt in zip(block, block[1:]):
                known = _literal_dict(prev)
                if known is None:
                    continue
                # Adjacent AST statements may be separated by a standalone
                # comment. Preserve that boundary rather than moving the
                # meaning of code around a user's comment.
                between = code.splitlines()[prev.end_lineno:next_stmt.lineno-1]
                if any(line.strip() for line in between):
                    continue
                name, mapping = known
                # Avoid ambiguous rebinding by comprehensions, nested defs,
                # assigned attributes, closures and scope trickery.
                if any(isinstance(n, (ast.Lambda, ast.FunctionDef,
                                      ast.AsyncFunctionDef, ast.ClassDef, ast.NamedExpr,
                                      ast.Yield, ast.YieldFrom, ast.Await))
                       for n in ast.walk(next_stmt)):
                    continue
                # Only read the dictionary. Do not allow assignment or deletion
                # to it in the following statement.
                if any(isinstance(n, ast.Name) and n.id == name
                       and isinstance(n.ctx, (ast.Store, ast.Del))
                       for n in ast.walk(next_stmt)):
                    continue
                calls = []
                for node in ast.walk(next_stmt):
                    if _eligible_lookup(node, name, mapping):
                        calls.append(node)
                if not calls:
                    continue
                # A statement containing *other* accesses to the same dict
                # could mutate it before evaluating a get, so skip all sites.
                # Only permit named references in recognized calls or their
                # `get` receiver. Literal assignment above is the only write.
                safe_ids = {id(n) for call in calls for n in ast.walk(call)}
                other_calls = [n for n in ast.walk(next_stmt)
                               if isinstance(n, ast.Call) and id(n) not in safe_ids]
                if other_calls:
                    continue
                for node in calls:
                    # Skip multiline expressions and comments within the span.
                    if node.lineno != node.end_lineno:
                        continue
                    if any(tok.type == tokenize.COMMENT and
                           tok.start[0] == node.lineno and
                           node.col_offset <= len(tok.line[:tok.start[1]].encode('utf-8')) < node.end_col_offset
                           for tok in tokens):
                        continue
                    key_node = node.args[0]
                    key_source = ast.get_source_segment(code, key_node)
                    if key_source is None or '\n' in key_source or '\r' in key_source:
                        continue
                    start = offsets[node.lineno-1] + node.col_offset
                    end = offsets[node.end_lineno-1] + node.end_col_offset
                    edits.append(_Edit(start, end, (name + '[' + key_source + ']').encode('utf-8')))
        if not edits:
            return code
        source = code.encode('utf-8')
        for edit in sorted(edits, key=lambda e:e.start, reverse=True):
            if edit.start < 0 or edit.end > len(source):
                return code
            source = source[:edit.start] + edit.text + source[edit.end:]
        result = source.decode('utf-8')
        ast.parse(result)
        after_comments, _ = _comment_tokens(result)
        if before_comments != after_comments:
            return code
        return result
    except (SyntaxError, UnicodeError, IndexError, TypeError, ValueError,
            tokenize.TokenError, IndentationError, RecursionError):
        return code
