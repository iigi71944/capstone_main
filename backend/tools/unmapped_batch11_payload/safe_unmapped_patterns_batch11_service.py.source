"""Batch 11 narrow transformations: literal zip, literal length, shallow list slice.

Only transform statically constrained examples. No changes to style storage/UI.
The source editor preserves unrelated comments and LF/CRLF bytes.
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


def _source_offsets(code: str) -> list[int]:
    offsets = [0]
    for line in code.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    return offsets


def _comments(code: str) -> set[tuple[int, int]]:
    return {token.start
            for token in tokenize.generate_tokens(io.StringIO(code).readline)
            if token.type == tokenize.COMMENT}


def _has_shadow(tree: ast.AST, builtin: str) -> bool:
    """Conservative whole-module builtin shadow check.

    Reject even a shadow in a different scope, plus implicit dynamic bindings.
    This is deliberately stricter than Python's lexical lookup rules.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in (builtin, '__builtins__'):
            if not isinstance(node.ctx, ast.Load):
                return True
        if isinstance(node, ast.arg) and node.arg == builtin:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == builtin:
                return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and builtin in node.names:
            return True
        if isinstance(node, ast.ExceptHandler) and node.name == builtin:
            return True
        if isinstance(node, ast.alias):
            if node.name == '*' or (node.asname or node.name.split('.')[0]) == builtin:
                return True
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == builtin:
            return True
        if isinstance(node, ast.MatchMapping) and node.rest == builtin:
            return True
    return False


def _literal_atom(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return type(node.value) in (int, float, str, bool, type(None))
    # Python's AST represents -1 as UnaryOp(USub, Constant(1)).
    return (isinstance(node, ast.UnaryOp)
            and isinstance(node.op, (ast.UAdd, ast.USub))
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in (int, float))


def _literal_sequence(node: ast.AST) -> bool:
    return isinstance(node, (ast.List, ast.Tuple)) and all(
        _literal_atom(item) for item in node.elts
    )


def _edit_expression(code: str, node: ast.AST, replacement: str,
                     offsets: list[int], commented: set[tuple[int, int]]) -> _Edit | None:
    if (getattr(node, 'end_lineno', None) is None
            or getattr(node, 'end_col_offset', None) is None):
        return None
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    # Preserve trailing comments outside the edited AST expression.
    lines = code.splitlines(keepends=True)
    for line, column in commented:
        comment_start = offsets[line - 1] + len(lines[line - 1][:column].encode('utf-8'))
        if start <= comment_start < end:
            return None
    return _Edit(start, end, replacement.encode('utf-8'))


def _apply_edits(code: str, edits: list[_Edit]) -> str:
    if not edits:
        return code
    selected: list[_Edit] = []
    for edit in sorted(edits, key=lambda item: item.end - item.start):
        if not any(edit.start < old.end and old.start < edit.end for old in selected):
            selected.append(edit)
    data = code.encode('utf-8')
    for edit in sorted(selected, key=lambda item: item.start, reverse=True):
        data = data[:edit.start] + edit.replacement + data[edit.end:]
    result = data.decode('utf-8')
    ast.parse(result)
    return result


def transform_to_safe_literal_len_style(code: str) -> str:
    """sum(1 for item in [literal, ...]) -> len([literal, ...]).

    Only single-generator, unconditional counting of static list/tuple elements.
    Never transforms arbitrary iterables, calls, or shadowed builtins.
    """
    try:
        tree = ast.parse(code)
        if _has_shadow(tree, 'sum') or _has_shadow(tree, 'len'):
            return code
        offsets, commented = _source_offsets(code), _comments(code)
        edits: list[_Edit] = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == 'sum'
                    and len(node.args) == 1 and not node.keywords):
                continue
            generator = node.args[0]
            if not (isinstance(generator, ast.GeneratorExp)
                    and _literal_atom(generator.elt) and type(generator.elt.value) is int
                    and generator.elt.value == 1 and len(generator.generators) == 1):
                continue
            gen = generator.generators[0]
            if (gen.is_async or gen.ifs or not isinstance(gen.target, ast.Name)
                    or not _literal_sequence(gen.iter)):
                continue
            source = ast.get_source_segment(code, gen.iter)
            if source is None:
                continue
            edit = _edit_expression(code, node, f'len({source})', offsets, commented)
            if edit:
                edits.append(edit)
        return _apply_edits(code, edits)
    except (SyntaxError, tokenize.TokenError, ValueError, UnicodeError):
        return code


def transform_to_safe_literal_zip_style(code: str) -> str:
    """for a,b in [(1,2),(3,4)] -> for a,b in zip((1,3),(2,4)).

    Each pair must contain literal primitive values, and zip must be unshadowed.
    Target assignment structure is preserved, including post-loop variables.
    """
    try:
        tree = ast.parse(code)
        if _has_shadow(tree, 'zip'):
            return code
        offsets, commented = _source_offsets(code), _comments(code)
        edits: list[_Edit] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.For):
                continue
            if not (isinstance(node.target, (ast.Tuple, ast.List))
                    and len(node.target.elts) == 2
                    and all(isinstance(item, ast.Name) for item in node.target.elts)):
                continue
            pairs = node.iter
            if not (isinstance(pairs, (ast.List, ast.Tuple)) and len(pairs.elts) >= 2):
                continue
            if any(not (isinstance(pair, (ast.Tuple, ast.List))
                        and len(pair.elts) == 2
                        and all(_literal_atom(atom) for atom in pair.elts))
                   for pair in pairs.elts):
                continue
            left = ', '.join(ast.unparse(pair.elts[0]) for pair in pairs.elts)
            right = ', '.join(ast.unparse(pair.elts[1]) for pair in pairs.elts)
            replacement = f'zip(({left}), ({right}))'
            edit = _edit_expression(code, pairs, replacement, offsets, commented)
            if edit:
                edits.append(edit)
        return _apply_edits(code, edits)
    except (SyntaxError, tokenize.TokenError, ValueError, UnicodeError):
        return code


def transform_to_safe_list_slice_style(code: str) -> str:
    """When a fresh list literal is immediately copied, use [:] not .copy().

    Matching fresh-list assignment must directly precede the copy within one
    statement block. Rewrites no other copy calls or object types.
    """
    try:
        tree = ast.parse(code)
        offsets, commented = _source_offsets(code), _comments(code)
        edits: list[_Edit] = []
        for node in ast.walk(tree):
            body = getattr(node, 'body', None)
            if not (isinstance(body, list) and body
                    and all(isinstance(stmt, ast.stmt) for stmt in body)):
                continue
            for first, second in zip(body, body[1:]):
                if not (isinstance(first, ast.Assign)
                        and len(first.targets) == 1 and isinstance(first.targets[0], ast.Name)
                        and isinstance(first.value, ast.List)):
                    continue
                name = first.targets[0].id
                # The simple variable assignment occurs before a copy, no
                # intervening operation or binding can replace that list.
                if isinstance(second, ast.Assign):
                    if len(second.targets) != 1:
                        continue
                    value = second.value
                elif isinstance(second, ast.Return):
                    value = second.value
                else:
                    continue
                if not (isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Attribute)
                        and value.func.attr == 'copy'
                        and isinstance(value.func.value, ast.Name)
                        and value.func.value.id == name
                        and not value.args and not value.keywords):
                    continue
                edit = _edit_expression(code, value, f'{name}[:]', offsets, commented)
                if edit:
                    edits.append(edit)
        return _apply_edits(code, edits)
    except (SyntaxError, tokenize.TokenError, ValueError, UnicodeError):
        return code
