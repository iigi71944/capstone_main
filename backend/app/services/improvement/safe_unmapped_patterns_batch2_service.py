"""Source-preserving, limited transformations for three additional concept tags.

These are opt-in through the existing saved concept tags; style persistence and
frontend are unchanged. A pre-existing execution verifier checks final code.
This module never runs submitted Python.

- Data transformation: list(map(str|int|abs, values)) -> list comprehension.
- Builtin usage: simple loop accumulation -> sum(...) (no observable loop var).
- Validation logic: nested if conditions -> one short-circuit AND condition.

The rules are intentionally *not* universal semantic-preservation proofs;
unsupported or ambiguous patterns remain byte-for-byte unchanged.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from typing import Iterator

_MAX_EDITS = 60
_DYNAMIC = frozenset({
    'locals', 'globals', 'vars', 'dir', 'eval', 'exec', 'compile',
    '__import__', 'inspect', 'sys', 'builtins', '__builtins__',
    'getattr', 'setattr', 'delattr', 'breakpoint',
})


def _parse(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, TypeError):
        return None


def _comments(source: str) -> set[int] | None:
    try:
        return {tok.start[0] for tok in tokenize.generate_tokens(io.StringIO(source).readline)
                if tok.type == tokenize.COMMENT}
    except (IndentationError, tokenize.TokenError):
        return None


def _shadowed_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split('.')[0])
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _unsafe(tree: ast.AST) -> bool:
    return any(isinstance(node, (ast.Global, ast.Nonlocal))
               or (isinstance(node, ast.Name) and node.id in _DYNAMIC)
               or (isinstance(node, (ast.Import, ast.ImportFrom)) and
                   any(a.name.split('.')[0] in _DYNAMIC or (a.asname or '') in _DYNAMIC
                       for a in node.names))
               for node in ast.walk(tree))


def _offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    return offsets


def _node_byte_span(node: ast.AST, offsets: list[int]) -> tuple[int, int] | None:
    l = getattr(node, 'lineno', None)
    end_l = getattr(node, 'end_lineno', None)
    start_c = getattr(node, 'col_offset', None)
    end_c = getattr(node, 'end_col_offset', None)
    if not (type(l) is int and type(end_l) is int
            and type(start_c) is int and type(end_c) is int
            and 1 <= l <= end_l < len(offsets)):
        return None
    return offsets[l-1] + start_c, offsets[end_l-1] + end_c


def _replace_bytes(source: str, edits: list[tuple[int, int, str]]) -> str:
    data = source.encode('utf-8')
    for start, end, replacement in sorted(edits, reverse=True):
        data = data[:start] + replacement.encode('utf-8') + data[end:]
    try:
        result = data.decode('utf-8')
    except UnicodeDecodeError:
        return source
    return result if _parse(result) is not None else source


def _literal_scalar(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return type(node.value) in (str, int, float, bool)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return (isinstance(node.operand, ast.Constant) and
                type(node.operand.value) in (int, float))
    return False


def _simple_iterable(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Load)
    if isinstance(node, (ast.List, ast.Tuple)):
        return len(node.elts) <= 30 and all(_literal_scalar(el) for el in node.elts)
    return False


def transform_to_data_comprehension(source: str) -> str:
    """Three examples: list(map(str|int|abs, simple_iterable))."""
    tree = _parse(source)
    comments = _comments(source) if tree is not None else None
    if tree is None or comments is None or _unsafe(tree):
        return source
    shadows = _shadowed_names(tree)
    if shadows & {'map', 'list'}:
        return source
    offsets = _offsets(source)
    all_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | shadows
    temp = next((f'__capstone_map_item_{idx}' for idx in range(100)
                 if f'__capstone_map_item_{idx}' not in all_names), None)
    if temp is None:
        return source
    edits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'list' and not node.keywords and len(node.args) == 1):
            continue
        mapped = node.args[0]
        if not (isinstance(mapped, ast.Call) and isinstance(mapped.func, ast.Name)
                and mapped.func.id == 'map' and len(mapped.args) == 2
                and not mapped.keywords and isinstance(mapped.args[0], ast.Name)
                and mapped.args[0].id in {'str', 'int', 'abs'}
                and mapped.args[0].id not in shadows
                and _simple_iterable(mapped.args[1])
                and node.lineno == node.end_lineno):
            continue
        if node.lineno in comments:
            continue
        iterable = ast.get_source_segment(source, mapped.args[1])
        if iterable is None or '\n' in iterable or '\r' in iterable:
            continue
        span = _node_byte_span(node, offsets)
        if span is None:
            continue
        before = source.encode('utf-8')[span[0]:span[1]].decode('utf-8')
        # Exclude unusual multiline or alternate token arrangements.
        if '\n' in before or '\r' in before:
            continue
        fn = mapped.args[0].id
        edits.append((span[0], span[1], f'[{fn}({temp}) for {temp} in {iterable}]'))
    return _replace_bytes(source, edits[:_MAX_EDITS]) if edits else source


def _safe_test(expr: ast.AST) -> bool:
    if isinstance(expr, ast.Name):
        return isinstance(expr.ctx, ast.Load)
    if isinstance(expr, ast.Constant):
        return type(expr.value) in (bool, int, float, str, type(None))
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _safe_test(expr.operand)
    if isinstance(expr, ast.Compare) and len(expr.ops) == 1:
        return (isinstance(expr.ops[0], (ast.Eq, ast.NotEq, ast.Lt,
                                        ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot))
                and _safe_test(expr.left) and _safe_test(expr.comparators[0]))
    return False


def _first_flatten_edit(source: str) -> tuple[int, int, str] | None:
    tree = _parse(source)
    comments = _comments(source) if tree is not None else None
    if tree is None or comments is None or _unsafe(tree):
        return None
    lines = source.splitlines(keepends=True)
    for outer in ast.walk(tree):
        if not (isinstance(outer, ast.If) and not outer.orelse and
                len(outer.body) == 1 and isinstance(outer.body[0], ast.If)
                and outer.end_lineno is not None and _safe_test(outer.test)):
            continue
        chain = [outer]
        current = outer
        while (len(chain) < 4 and len(current.body) == 1
               and isinstance(current.body[0], ast.If) and not current.body[0].orelse
               and _safe_test(current.body[0].test)):
            current = current.body[0]
            chain.append(current)
        if len(chain) < 2 or not current.body or current.end_lineno is None:
            continue
        if any(node.test.end_lineno != node.lineno or node.test.lineno != node.lineno
               for node in chain):
            continue
        if any(node.lineno in comments for node in chain):
            continue
        start, end = outer.lineno, outer.end_lineno
        if any(start <= row <= end for row in comments):
            continue
        headers = [lines[node.lineno-1] for node in chain]
        matched = [re.match(r'^([ \t]*)if\s+.+:\s*(?:\r?\n|\r)$', line)
                   for line in headers]
        if any(m is None for m in matched):
            continue
        indents = [m.group(1) for m in matched]
        steps = [indents[idx][len(indents[idx-1]):]
                 if indents[idx].startswith(indents[idx-1]) else ''
                 for idx in range(1, len(indents))]
        if not steps or any(not step or '\t' in step and ' ' in step for step in steps):
            continue
        if len(set(steps)) != 1:
            continue
        unit = steps[0]
        inner_line = lines[current.body[0].lineno - 1]
        inner_indent = inner_line[:len(inner_line) - len(inner_line.lstrip(' \t'))]
        if not inner_indent.startswith(indents[-1] + unit):
            continue
        tests = [ast.get_source_segment(source, n.test) for n in chain]
        if any(t is None or '\n' in t or '\r' in t for t in tests):
            continue
        eol = '\r\n' if headers[0].endswith('\r\n') else '\n' if headers[0].endswith('\n') else '\r'
        body_start = current.body[0].lineno
        # A nested `if` with only one item makes this safe: trim inner header lines.
        body_rows = lines[body_start - 1:end]
        nlevels = len(chain)-1
        transformed = []
        for row in body_rows:
            if row.strip():
                remove = unit * nlevels
                if not row.startswith(indents[0] + remove):
                    transformed = []
                    break
                transformed.append(row[:len(indents[0])] + row[len(indents[0]+remove):])
            else:
                transformed.append(row)
        if not transformed:
            continue
        header = indents[0] + 'if ' + ' and '.join(f'({test.strip()})' for test in tests) + ':' + eol
        replacement = header + ''.join(transformed)
        trial = ''.join(lines[:start-1]) + replacement + ''.join(lines[end:])
        if _parse(trial) is None:
            continue
        return start-1, end, replacement
    return None


def transform_to_validation_condition(source: str) -> str:
    """Three patterns: 2-level, 3-level, and function-scope nested condition."""
    if not isinstance(source, str):
        return source
    for _ in range(_MAX_EDITS):
        edit = _first_flatten_edit(source)
        if edit is None:
            return source
        start, end, replacement = edit
        lines = source.splitlines(keepends=True)
        trial = ''.join(lines[:start]) + replacement + ''.join(lines[end:])
        if trial == source:
            return source
        source = trial
    return source


def _sum_rhs(stmt: ast.stmt, accumulator: str, element: str) -> bool:
    if isinstance(stmt, ast.AugAssign):
        return (isinstance(stmt.op, ast.Add) and isinstance(stmt.target, ast.Name)
                and stmt.target.id == accumulator
                and isinstance(stmt.value, ast.Name) and stmt.value.id == element)
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        expr = stmt.value
        return (isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == accumulator
                and isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add)
                and isinstance(expr.left, ast.Name) and expr.left.id == accumulator
                and isinstance(expr.right, ast.Name) and expr.right.id == element)
    return False


def _sum_rewrites(source: str) -> list[tuple[int, int, str]]:
    tree = _parse(source)
    comments = _comments(source) if tree is not None else None
    if tree is None or comments is None or _unsafe(tree) or 'sum' in _shadowed_names(tree):
        return []
    lines = source.splitlines(keepends=True)
    offsets = _offsets(source)
    edits: list[tuple[int, int, str]] = []
    for parent in ast.walk(tree):
        for _field, body in ast.iter_fields(parent):
            if not (isinstance(body, list) and len(body) >= 2
                    and all(isinstance(s, ast.stmt) for s in body)):
                continue
            for i, (assign, loop) in enumerate(zip(body, body[1:])):
                if not (isinstance(assign, ast.Assign) and len(assign.targets) == 1
                        and isinstance(assign.targets[0], ast.Name)
                        and isinstance(assign.value, ast.Constant)
                        and type(assign.value.value) is int and assign.value.value == 0
                        and isinstance(loop, ast.For) and not loop.orelse
                        and len(loop.body) == 1 and isinstance(loop.target, ast.Name)
                        and _simple_iterable(loop.iter)):
                    continue
                accum, elem = assign.targets[0].id, loop.target.id
                if accum == elem or accum in _DYNAMIC or elem in _DYNAMIC:
                    continue
                predicate = None
                value_stmt = loop.body[0]
                if (isinstance(value_stmt, ast.If) and not value_stmt.orelse
                        and len(value_stmt.body) == 1 and _safe_test(value_stmt.test)):
                    predicate = value_stmt.test
                    value_stmt = value_stmt.body[0]
                if not _sum_rhs(value_stmt, accum, elem):
                    continue
                if predicate and any(isinstance(n, ast.Name) and n.id == accum
                                     for n in ast.walk(predicate)):
                    continue
                # Changing a `for` loop removes its final loop target binding.
                # Reject ANY reference outside the transformed loop, including
                # closures declared before the loop and uses in sibling scopes.
                loop_nodes = {id(n) for n in ast.walk(loop)}
                if any(isinstance(n, ast.Name) and n.id == elem and id(n) not in loop_nodes
                       for n in ast.walk(tree)):
                    continue
                # Source-level replacement requires separate physical lines and
                # no comments within the block (including inline comments).
                if (assign.end_lineno != assign.lineno or
                        loop.end_lineno is None or
                        loop.lineno <= assign.end_lineno or
                        any(assign.lineno <= row <= loop.end_lineno for row in comments)):
                    continue
                start_line, end_line = assign.lineno, loop.end_lineno
                indent = re.match(r'^[ \t]*', lines[start_line-1]).group()
                loop_indent = re.match(r'^[ \t]*', lines[loop.lineno-1]).group()
                if indent != loop_indent:
                    continue
                iterable = ast.get_source_segment(source, loop.iter)
                if iterable is None or '\n' in iterable or '\r' in iterable:
                    continue
                if predicate is None:
                    argument = iterable
                else:
                    test_src = ast.get_source_segment(source, predicate)
                    if test_src is None or '\n' in test_src or '\r' in test_src:
                        continue
                    argument = f'({elem} for {elem} in {iterable} if {test_src})'
                eol = '\r\n' if lines[start_line-1].endswith('\r\n') else '\n'
                fragment = f'{indent}{accum} = sum({argument})' + eol
                start, end = offsets[start_line-1], offsets[end_line]
                edits.append((start, end, fragment))
                if len(edits) >= _MAX_EDITS:
                    return edits
    return edits


def transform_to_builtin_sum(source: str) -> str:
    """Three patterns: augassign, explicit addition, predicate-count filter."""
    if not isinstance(source, str):
        return source
    edits = _sum_rewrites(source)
    if not edits:
        return source
    return _replace_bytes(source, edits)
