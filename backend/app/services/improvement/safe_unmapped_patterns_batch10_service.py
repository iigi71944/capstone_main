"""Batch 10 conservative additions: integer augmented assignment and enumerate.

No execution of untrusted input. Only source-level edits of restricted patterns;
unsupported input remains unchanged. This is not a semantic equivalence proof
for arbitrary Python environments, instrumentation, or concurrency.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: str


def _offsets(source: str) -> list[int]:
    positions = [0]
    for line in source.splitlines(keepends=True):
        positions.append(positions[-1] + len(line.encode('utf-8')))
    return positions


def _span(positions: list[int], node: ast.AST) -> tuple[int, int] | None:
    if not (hasattr(node, 'lineno') and hasattr(node, 'end_lineno')):
        return None
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    return positions[node.lineno - 1] + node.col_offset, positions[node.end_lineno - 1] + node.end_col_offset


def _apply(source: str, edits: list[_Edit]) -> str:
    if not edits:
        return source
    changed = source.encode('utf-8')
    previous_start = len(changed)
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        if edit.end > previous_start or edit.start < 0 or edit.end > len(changed):
            return source
        previous_start = edit.start
        changed = changed[:edit.start] + edit.replacement.encode('utf-8') + changed[edit.end:]
    result = changed.decode('utf-8')
    ast.parse(result)
    return result


def _literal_int(node: ast.AST) -> int | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, OverflowError, RecursionError, MemoryError):
        return None
    return value if type(value) is int and abs(value) <= 1000000000 else None


def _standalone(source_lines: list[str], node: ast.stmt) -> bool:
    if node.end_lineno != node.lineno or node.end_col_offset is None:
        return False
    if not (1 <= node.lineno <= len(source_lines)):
        return False
    line = source_lines[node.lineno - 1].encode('utf-8')
    return not line[:node.col_offset].strip() and not line[node.end_col_offset:].strip()


def _bodies(tree: ast.AST):
    """Only modules and synchronous functions; no class, condition, try or loop scope."""
    if isinstance(tree, (ast.Module, ast.FunctionDef)):
        yield tree.body
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node is not tree:
                yield node.body


def transform_to_safe_augassign_style(source: str) -> str:
    """`x = 6; x = x + 2` -> `x = 6; x += 2` for known plain integers."""
    try:
        tree = ast.parse(source)
        positions = _offsets(source)
        lines = source.splitlines(keepends=True)
        edits: list[_Edit] = []
        for body in _bodies(tree):
            for left, right in zip(body, body[1:]):
                if not (isinstance(left, ast.Assign) and isinstance(right, ast.Assign)
                        and len(left.targets) == len(right.targets) == 1
                        and isinstance(left.targets[0], ast.Name)
                        and isinstance(right.targets[0], ast.Name)
                        and left.targets[0].id == right.targets[0].id
                        and right.lineno == left.end_lineno + 1
                        and left.col_offset == right.col_offset
                        and _standalone(lines, right)):
                    continue
                name = left.targets[0].id
                if _literal_int(left.value) is None:
                    continue
                expr = right.value
                if not (isinstance(expr, ast.BinOp)
                        and isinstance(expr.left, ast.Name) and expr.left.id == name
                        and isinstance(expr.op, (ast.Add, ast.Sub, ast.Mult))
                        and _literal_int(expr.right) is not None):
                    continue
                if any(isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names
                       for stmt in body for node in ast.walk(stmt)):
                    continue
                operator = {ast.Add: '+=', ast.Sub: '-=', ast.Mult: '*='}[type(expr.op)]
                segment = _span(positions, right)
                if segment is None:
                    continue
                edits.append(_Edit(*segment, f'{name} {operator} {ast.unparse(expr.right)}'))
        return _apply(source, edits)
    except (SyntaxError, UnicodeError, ValueError, OverflowError, RecursionError, IndexError):
        return source


def _shadows_builtin(tree: ast.AST, *names: str) -> bool:
    names = set(names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg in names:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names:
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) in names:
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and names.intersection(node.names):
            return True
        if isinstance(node, ast.ImportFrom) and any(a.name == '*' for a in node.names):
            return True
    return False


def _plain_container(stmt: ast.stmt, name: str) -> bool:
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == name
            and isinstance(stmt.value, (ast.Tuple, ast.List))):
        return False
    elements = stmt.value.elts
    for item in elements:
        try:
            value = ast.literal_eval(item)
        except (ValueError, TypeError, RecursionError, MemoryError):
            return False
        if type(value) not in (int, str, bool, type(None)):
            return False
    return True


def _preconditions(body: list[ast.stmt], index: int, name: str) -> tuple[bool, set[str]]:
    """Require a literal sequence close to the loop and separately fresh output lists."""
    preceding = body[max(0, index - 3):index]
    source_pos = [n for n, stmt in enumerate(preceding) if _plain_container(stmt, name)]
    if len(source_pos) != 1:
        return False, set()
    after = preceding[source_pos[0] + 1:]
    output_names: set[str] = set()
    for stmt in after:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id != name
                and isinstance(stmt.value, ast.List) and not stmt.value.elts):
            return False, set()
        output_names.add(stmt.targets[0].id)
    return True, output_names


def _allowed_loop_body(statements: list[ast.stmt], data: str, index: str,
                       outputs: set[str]) -> bool:
    """Calls limited to print(...) and append(...) on a known fresh result list."""
    def walk_statement(stmt: ast.stmt) -> bool:
        if isinstance(stmt, ast.If):
            return (not stmt.orelse and all(_pure_expression(n) for n in [stmt.test])
                    and all(walk_statement(child) for child in stmt.body))
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if isinstance(call.func, ast.Name) and call.func.id == 'print':
                return not call.keywords and all(_pure_expression(arg) for arg in call.args)
            if (isinstance(call.func, ast.Attribute) and call.func.attr == 'append'
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id in outputs):
                return len(call.args) == 1 and not call.keywords and _pure_expression(call.args[0])
            return False
        if isinstance(stmt, ast.AugAssign):
            return (isinstance(stmt.target, ast.Name)
                    and stmt.target.id not in (data, index)
                    and isinstance(stmt.op, (ast.Add, ast.Sub))
                    and _pure_expression(stmt.value))
        if isinstance(stmt, ast.Assign):
            return (len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                    and stmt.targets[0].id not in (data, index)
                    and _pure_expression(stmt.value))
        return False

    def _pure_expression(expr: ast.AST) -> bool:
        return not any(isinstance(n, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom,
                                      ast.NamedExpr, ast.Lambda, ast.GeneratorExp,
                                      ast.ListComp, ast.DictComp, ast.SetComp,
                                      ast.Attribute))
                       for n in ast.walk(expr))

    return bool(statements) and all(walk_statement(stmt) for stmt in statements)


def transform_to_safe_enumerate_style(source: str) -> str:
    """`for i in range(len(items))` -> `for i, item in enumerate(items)`.

    Only a newly assigned literal list/tuple, limited read-only loop body,
    with explicit source segment replacements. Does not touch unsupported loops.
    """
    try:
        tree = ast.parse(source)
        if _shadows_builtin(tree, 'range', 'len', 'enumerate', 'print'):
            return source
        positions = _offsets(source)
        lines = source.splitlines(keepends=True)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
        edits: list[_Edit] = []
        for body in _bodies(tree):
            for idx, loop in enumerate(body):
                if not (isinstance(loop, ast.For) and isinstance(loop.target, ast.Name)
                        and not loop.orelse and loop.lineno == loop.iter.lineno
                        and loop.lineno == loop.target.lineno
                        and loop.body and loop.body[0].lineno > loop.lineno):
                    continue
                index_name = loop.target.id
                call = loop.iter
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id == 'range' and len(call.args) == 1
                        and not call.keywords):
                    continue
                length = call.args[0]
                if not (isinstance(length, ast.Call) and isinstance(length.func, ast.Name)
                        and length.func.id == 'len' and len(length.args) == 1
                        and not length.keywords and isinstance(length.args[0], ast.Name)):
                    continue
                data_name = length.args[0].id
                if data_name == index_name:
                    continue
                known, outputs = _preconditions(body, idx, data_name)
                if not known or not _allowed_loop_body(loop.body, data_name, index_name, outputs):
                    continue
                if any(isinstance(n, ast.Name) and n.id in (data_name, index_name)
                       and isinstance(n.ctx, (ast.Store, ast.Del)) for s in loop.body for n in ast.walk(s)):
                    continue
                if not (1 <= loop.lineno <= len(lines)):
                    continue
                header = lines[loop.lineno - 1].encode('utf-8')
                if b'#' in header or header[loop.iter.end_col_offset:].strip() != b':':
                    continue
                target_span = _span(positions, loop.target)
                iter_span = _span(positions, loop.iter)
                if target_span is None or iter_span is None:
                    continue
                replacements = []
                for s in loop.body:
                    for sub in ast.walk(s):
                        if (isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name)
                                and sub.value.id == data_name and isinstance(sub.slice, ast.Name)
                                and sub.slice.id == index_name and isinstance(sub.ctx, ast.Load)):
                            replacements.append(sub)
                if not replacements:
                    continue
                new_var = '__capstone_item'
                suffix = 1
                while new_var in used:
                    new_var = f'__capstone_item_{suffix}'
                    suffix += 1
                used.add(new_var)
                edits.extend((_Edit(*target_span, f'{index_name}, {new_var}'),
                              _Edit(*iter_span, f'enumerate({data_name})')))
                for sub in replacements:
                    sub_span = _span(positions, sub)
                    if sub_span is not None:
                        edits.append(_Edit(*sub_span, new_var))
        return _apply(source, edits)
    except (SyntaxError, UnicodeError, ValueError, OverflowError, RecursionError, IndexError):
        return source
