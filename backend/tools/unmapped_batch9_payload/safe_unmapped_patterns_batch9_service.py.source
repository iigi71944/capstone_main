"""Conservative, source-to-source transformations for three new syntax tags.

Only touch source proven to be in the narrow supported grammar.  All other
Python remains unchanged. No runtime evaluation of user-provided code.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: str


def _splice(code: str, edits: list[_Edit]) -> str:
    if not edits:
        return code
    data = code.encode('utf-8')
    converted = [(item.start, item.end, item.replacement.encode('utf-8')) for item in edits]
    for start, end, text in sorted(converted, reverse=True):
        data = data[:start] + text + data[end:]
    return data.decode('utf-8')


def _position_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    return offsets


def _node_span(offsets: list[int], node: ast.AST) -> tuple[int, int] | None:
    if not (hasattr(node, 'lineno') and hasattr(node, 'end_lineno')):
        return None
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    return (offsets[node.lineno - 1] + node.col_offset,
            offsets[node.end_lineno - 1] + node.end_col_offset)


def _has_range_shadow(tree: ast.AST) -> bool:
    # Avoid injecting any builtin range() call when name resolution can differ.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == 'range' and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg == 'range':
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == 'range':
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) == 'range':
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and 'range' in node.names:
            return True
        if isinstance(node, ast.ImportFrom) and any(alias.name == '*' for alias in node.names):
            return True
    return False


def _simple_int(node: ast.AST) -> int | None:
    if not isinstance(node, (ast.Constant, ast.UnaryOp)):
        return None
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, MemoryError):
        return None
    return value if type(value) is int else None


def transform_to_literal_range_style(code: str) -> str:
    """Rewrite `for i in [2,4,6]:` -> `for i in range(2,8,2):`.

    Recognizes arithmetic sequences of 3-20 built-in integers only. Never
    transforms dynamic expressions, range shadows or nested special cases.
    """
    try:
        tree = ast.parse(code)
        if _has_range_shadow(tree):
            return code
        offsets = _position_offsets(code)
        edits = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.For) or not isinstance(node.iter, (ast.List, ast.Tuple)):
                continue
            elements = node.iter.elts
            if not 3 <= len(elements) <= 20:
                continue
            ints = [_simple_int(item) for item in elements]
            if any(value is None for value in ints):
                continue
            step = ints[1] - ints[0]
            if step == 0 or any(b - a != step for a, b in zip(ints, ints[1:])):
                continue
            start, stop = ints[0], ints[-1] + step
            if step == 1 and start == 0:
                replacement = f'range({stop})'
            elif step == 1:
                replacement = f'range({start}, {stop})'
            else:
                replacement = f'range({start}, {stop}, {step})'
            span = _node_span(offsets, node.iter)
            if span is not None:
                edits.append(_Edit(*span, replacement))
        if not edits:
            return code
        result = _splice(code, edits)
        ast.parse(result)
        return result
    except (SyntaxError, UnicodeError, ValueError, OverflowError):
        return code


def _known_literal(statement: ast.stmt) -> tuple[str, type] | None:
    if not (isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)):
        return None
    try:
        value = ast.literal_eval(statement.value)
    except (ValueError, TypeError, MemoryError):
        return None
    if type(value) not in (int, str):
        return None
    return statement.targets[0].id, type(value)


def _members(test: ast.AST, name: str, literal_type: type) -> list[int | str] | None:
    if not isinstance(test, ast.BoolOp) or not isinstance(test.op, ast.Or):
        return None
    if not 2 <= len(test.values) <= 8:
        return None
    values = []
    for item in test.values:
        if not (isinstance(item, ast.Compare)
                and len(item.ops) == 1 and isinstance(item.ops[0], ast.Eq)
                and len(item.comparators) == 1
                and isinstance(item.left, ast.Name) and item.left.id == name
                and isinstance(item.comparators[0], (ast.Constant, ast.UnaryOp))):
            return None
        try:
            value = ast.literal_eval(item.comparators[0])
        except (ValueError, TypeError, MemoryError):
            return None
        if type(value) is not literal_type:
            return None
        values.append(value)
    return values


def transform_to_known_membership_style(code: str) -> str:
    """Turn adjacent literal-bound equality ORs into membership.

    `x = 2; if x == 1 or x == 2:` -> `if x in (1, 2):`
    Only an immediately preceding literal assignment establishes the primitive
    type: no user-defined __eq__, call side effects or repeated name loads.
    """
    try:
        tree = ast.parse(code)
        offsets = _position_offsets(code)
        edits = []

        def inspect(body: list[ast.stmt]) -> None:
            for first, second in zip(body, body[1:]):
                known = _known_literal(first)
                if not known or not isinstance(second, ast.If):
                    continue
                name, literal_type = known
                values = _members(second.test, name, literal_type)
                if values is None:
                    continue
                span = _node_span(offsets, second.test)
                if span is not None:
                    members = ', '.join(repr(v) for v in values)
                    edits.append(_Edit(*span, f'{name} in ({members})'))

        # Only inspect local statement lists of Module/FunctionDef and nested
        # statement scopes, not different scopes considered adjacent.
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.If, ast.For, ast.While, ast.With, ast.Try)):
                for attr in ('body', 'orelse', 'finalbody'):
                    block = getattr(node, attr, None)
                    if isinstance(block, list):
                        inspect(block)
        if not edits:
            return code
        result = _splice(code, edits)
        ast.parse(result)
        return result
    except (SyntaxError, UnicodeError, ValueError):
        return code


class _NestedIfMerge(ast.NodeTransformer):
    def __init__(self):
        self.changed = False

    def visit_If(self, node: ast.If):
        self.generic_visit(node)
        if node.orelse or len(node.body) != 1:
            return node
        inner = node.body[0]
        if not isinstance(inner, ast.If) or inner.orelse:
            return node
        # Both conditions have identical short-circuit evaluation in `and`.
        self.changed = True
        return ast.copy_location(ast.If(
            test=ast.BoolOp(op=ast.And(), values=[node.test, inner.test]),
            body=inner.body,
            orelse=[],
        ), node)


def transform_to_nested_boolean_style(code: str) -> str:
    """Merge `if a: if b:` into `if a and b:` without touching if/else."""
    try:
        tree = ast.parse(code)
        t = _NestedIfMerge()
        tree = t.visit(tree)
        if not t.changed:
            return code
        ast.fix_missing_locations(tree)
        result = ast.unparse(tree)
        ast.parse(result)
        return result
    except (SyntaxError, ValueError, TypeError):
        return code
