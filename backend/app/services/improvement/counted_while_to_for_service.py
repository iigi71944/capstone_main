"""Convert statically bounded integer-counter while loops into for/range.

Ownership: this transformer handles while -> for only. The for -> while
transformer uses iterator semantics in for_to_while_service.py.

Supported: signed integer steps, += / -= / ordinary assignments, reversed
comparison operands, inclusive boundaries, proven integer limit variables,
and len() of locally initialized literal collections. Unproven or dynamic
bounds remain while loops, because range() evaluates bounds only once.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass

from app.services.improvement.for_iterator_to_for_service import (
    restore_iterator_for_loops,
)


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes


def _int_literal(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _int_literal(node.operand)
        if value is not None:
            return -value if isinstance(node.op, ast.USub) else value
    return None


def _step(stmt: ast.stmt) -> tuple[str, int] | None:
    if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
        value = _int_literal(stmt.value)
        if value is not None:
            if isinstance(stmt.op, ast.Add):
                return stmt.target.id, value
            if isinstance(stmt.op, ast.Sub):
                return stmt.target.id, -value
    if not (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and isinstance(stmt.value, ast.BinOp)
    ):
        return None
    name = stmt.targets[0].id
    expr = stmt.value
    if isinstance(expr.op, ast.Add):
        if isinstance(expr.left, ast.Name) and expr.left.id == name:
            amount = _int_literal(expr.right)
            if amount is not None:
                return name, amount
        if isinstance(expr.right, ast.Name) and expr.right.id == name:
            amount = _int_literal(expr.left)
            if amount is not None:
                return name, amount
    if isinstance(expr.op, ast.Sub):
        if isinstance(expr.left, ast.Name) and expr.left.id == name:
            amount = _int_literal(expr.right)
            if amount is not None:
                return name, -amount
    return None


def _condition(test: ast.AST, counter: str, step: int):
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and len(test.comparators) == 1):
        return None
    left, right, operator = test.left, test.comparators[0], test.ops[0]
    if isinstance(left, ast.Name) and left.id == counter:
        bound = right
    elif isinstance(right, ast.Name) and right.id == counter:
        bound = left
        invert = {
            ast.Lt: ast.Gt, ast.LtE: ast.GtE,
            ast.Gt: ast.Lt, ast.GtE: ast.LtE,
        }
        if type(operator) not in invert:
            return None
        operator = invert[type(operator)]()
    else:
        return None
    if not isinstance(operator, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
        return None
    if step > 0 and not isinstance(operator, (ast.Lt, ast.LtE)):
        return None
    if step < 0 and not isinstance(operator, (ast.Gt, ast.GtE)):
        return None
    if _int_literal(bound) is not None:
        text, dependency, kind = repr(_int_literal(bound)), None, "constant"
    elif isinstance(bound, ast.Name) and bound.id != counter:
        text, dependency, kind = bound.id, bound.id, "name"
    elif (
        isinstance(bound, ast.Call)
        and isinstance(bound.func, ast.Name)
        and bound.func.id == "len"
        and len(bound.args) == 1
        and not bound.keywords
        and isinstance(bound.args[0], ast.Name)
        and bound.args[0].id != counter
    ):
        text = f"len({bound.args[0].id})"
        dependency, kind = bound.args[0].id, "length"
    else:
        return None
    if isinstance(operator, ast.LtE):
        text = f"({text}) + 1"
    elif isinstance(operator, ast.GtE):
        text = f"({text}) - 1"
    return text, dependency, kind


def _shadowed_builtin(tree: ast.AST, names: set[str]) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg in names:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names:
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) in names:
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and set(node.names) & names:
            return True
    return False


def _simple_binding(stmt: ast.stmt, name: str) -> ast.expr | None:
    if (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and stmt.targets[0].id == name
    ):
        return stmt.value
    return None


def _has_fixed_binding(body: list[ast.stmt], position: int, name: str, kind: str) -> bool:
    """Require a literal counter / limit before the loop in its own block."""
    for stmt in reversed(body[:position]):
        value = _simple_binding(stmt, name)
        if value is None:
            # Only permit intervening simple, independent assignments.
            if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                return False
            for part in ast.walk(stmt):
                if isinstance(part, ast.Name) and part.id == name:
                    return False
            continue
        if kind == "int":
            return _int_literal(value) is not None
        if kind == "length":
            return (
                isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict))
                and not any(isinstance(x, (ast.Starred, ast.Call)) for x in ast.walk(value))
            ) or (isinstance(value, ast.Constant) and isinstance(value.value, (str, bytes)))
    return False


def _aliased_before_loop(body: list[ast.stmt], position: int, name: str) -> bool:
    """Do not freeze len(name) when another local may mutate the same list."""
    for stmt in body[:position]:
        for part in ast.walk(stmt):
            if isinstance(part, (ast.Assign, ast.NamedExpr)):
                value = part.value
                if isinstance(value, ast.Name) and value.id == name:
                    return True
    return False


def _body_safe(node: ast.While, counter: str, dependency: str | None) -> bool:
    if not node.body or _step(node.body[-1]) is None:
        return False
    for statement in node.body[:-1]:
        for part in ast.walk(statement):
            if isinstance(part, (ast.Continue, ast.Yield, ast.YieldFrom, ast.Await)):
                return False
            if isinstance(part, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                return False
            if isinstance(part, (ast.Global, ast.Nonlocal)):
                return False
            if isinstance(part, ast.Name) and isinstance(part.ctx, (ast.Store, ast.Del)):
                if part.id in {counter, dependency}:
                    return False
            # Any call receiving the bound container or calling methods on it
            # could change len(container) between iterations.
            if dependency is not None and isinstance(part, ast.Call):
                if isinstance(part.func, ast.Attribute) and isinstance(part.func.value, ast.Name):
                    if part.func.value.id == dependency:
                        return False
                if any(
                    isinstance(child, ast.Name) and child.id == dependency
                    for arg in [*part.args, *(kw.value for kw in part.keywords)]
                    for child in ast.walk(arg)
                ):
                    if not (isinstance(part.func, ast.Name) and part.func.id == "print"):
                        return False
    return True


def _header_edit(code: str, node: ast.While, counter: str, stop: str, step: int):
    if node.test.lineno != node.lineno or node.test.end_lineno != node.lineno:
        return None
    lines = code.splitlines(keepends=True)
    line = lines[node.lineno - 1]
    ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    raw = line[:-len(ending)] if ending else line
    prefix = raw[:node.col_offset]
    if prefix.strip() or not raw[node.col_offset:].startswith(("while ", "while(")):
        return None
    depth = 0
    colon = None
    try:
        for token in tokenize.generate_tokens(io.StringIO(raw + "\n").readline):
            if token.type != tokenize.OP:
                continue
            if token.string in "([{":
                depth += 1
            elif token.string in ")]}":
                depth -= 1
            elif token.string == ":" and depth == 0:
                colon = token.start[1]
                break
    except tokenize.TokenError:
        return None
    if colon is None:
        return None
    tail = raw[colon + 1:]
    if tail.strip() and not tail.lstrip().startswith("#"):
        return None
    arguments = f"{counter}, {stop}" if step == 1 else f"{counter}, {stop}, {step}"
    replacement = f"{prefix}for {counter} in range({arguments}):{tail}{ending}"
    start = sum(len(ln.encode("utf-8")) for ln in lines[:node.lineno - 1])
    return _Edit(start, start + len(line.encode("utf-8")), replacement.encode("utf-8"))


def _candidate_blocks(tree: ast.AST):
    """Find loops together with their directly enclosing statement lists."""
    for scope in ast.walk(tree):
        for _, value in ast.iter_fields(scope):
            if not isinstance(value, list):
                continue
            if not value or not all(isinstance(x, ast.stmt) for x in value):
                continue
            for index, stmt in enumerate(value):
                if isinstance(stmt, ast.While):
                    yield value, index, stmt


def transform_counted_while_to_for(code: str) -> str:
    """Restore lowered for-loops, then convert safe integer-counter while."""
    code = restore_iterator_for_loops(code)
    try:
        tree = ast.parse(code)
        if _shadowed_builtin(tree, {"range", "len"}):
            return code
        edits: list[_Edit] = []
        for body, position, node in _candidate_blocks(tree):
            if not node.body:
                continue
            update = _step(node.body[-1])
            if update is None:
                continue
            counter, step = update
            if step == 0 or abs(step) > 1000000:
                continue
            if not _has_fixed_binding(body, position, counter, "int"):
                continue
            check = _condition(node.test, counter, step)
            if check is None:
                continue
            stop, dependency, kind = check
            if dependency is not None:
                binding_kind = "length" if kind == "length" else "int"
                if not _has_fixed_binding(body, position, dependency, binding_kind):
                    continue
                if kind == "length" and _aliased_before_loop(body, position, dependency):
                    continue
            if not _body_safe(node, counter, dependency):
                continue
            edit = _header_edit(code, node, counter, stop, step)
            if edit is not None:
                edits.append(edit)
        if not edits:
            return code
        result = code.encode("utf-8")
        for edit in sorted(edits, key=lambda e: e.start, reverse=True):
            result = result[:edit.start] + edit.replacement + result[edit.end:]
        output = result.decode("utf-8")
        ast.parse(output)
        return output
    except (SyntaxError, UnicodeError, tokenize.TokenError, ValueError):
        return code
