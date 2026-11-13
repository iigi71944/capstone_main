"""Conservatively convert counted while loops to for/range loops.

This feature only handles while loops. Existing direct/index/for-to-while
transformers retain their responsibilities. The final counter update stays
in the loop body so values after the loop are preserved.

Examples:
    index = 0
    while index < len(items):
        print(items[index])
        index += 1

    index = 0
    for index in range(index, len(items)):
        print(items[index])
        index += 1

The redundant-looking increment is intentional: removing it changes the
counter's final value after the loop (and can affect closure observability).
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


def _integer_constant(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _integer_constant(node.operand)
        return -value if value is not None else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _integer_constant(node.operand)
    return None


def _counter_step(node: ast.stmt) -> tuple[str, int] | None:
    if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
        increment = _integer_constant(node.value)
        if increment is None:
            return None
        if isinstance(node.op, ast.Add):
            return node.target.id, increment
        if isinstance(node.op, ast.Sub):
            return node.target.id, -increment
        return None

    if not (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.BinOp)
    ):
        return None

    name = node.targets[0].id
    expression = node.value
    if isinstance(expression.op, ast.Add):
        if isinstance(expression.left, ast.Name) and expression.left.id == name:
            amount = _integer_constant(expression.right)
            if amount is not None:
                return name, amount
        if isinstance(expression.right, ast.Name) and expression.right.id == name:
            amount = _integer_constant(expression.left)
            if amount is not None:
                return name, amount
    if isinstance(expression.op, ast.Sub):
        if isinstance(expression.left, ast.Name) and expression.left.id == name:
            amount = _integer_constant(expression.right)
            if amount is not None:
                return name, -amount
    return None


def _bound_expression(node: ast.AST, index_name: str) -> tuple[str, str | None] | None:
    """Return pure integer expression text and optional sequence dependency.

    Name bounds are allowed if not assigned in the body. Noninteger runtime
    values may be rejected by range(); unchanged behavior is therefore not
    guaranteed for arbitrary user-supplied parameter types. The enclosing
    runtime equivalence check must still run for every applied transformation.
    """
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return repr(node.value), None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _bound_expression(node.operand, index_name)
        if inner is None:
            return None
        return ("-" if isinstance(node.op, ast.USub) else "+") + f"({inner[0]})", inner[1]
    if isinstance(node, ast.Name) and node.id != index_name:
        return node.id, node.id
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
        and len(node.args) == 1
        and not node.keywords
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id != index_name
    ):
        return f"len({node.args[0].id})", node.args[0].id
    return None


def _inverted_operator(operator: ast.cmpop) -> ast.cmpop:
    inverse = {ast.Lt: ast.Gt, ast.LtE: ast.GtE, ast.Gt: ast.Lt, ast.GtE: ast.LtE}
    return inverse[type(operator)]()


def _condition(node: ast.AST, counter: str, step: int) -> tuple[str, str | None] | None:
    if not (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and len(node.comparators) == 1
    ):
        return None
    left, right, operator = node.left, node.comparators[0], node.ops[0]
    if isinstance(left, ast.Name) and left.id == counter:
        bound_node = right
    elif isinstance(right, ast.Name) and right.id == counter:
        if not isinstance(operator, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
            return None
        bound_node = left
        operator = _inverted_operator(operator)
    else:
        return None

    bound = _bound_expression(bound_node, counter)
    if bound is None:
        return None
    text, dependency = bound
    if step > 0:
        if isinstance(operator, ast.Lt):
            stop = text
        elif isinstance(operator, ast.LtE):
            stop = f"({text}) + 1"
        else:
            return None
    else:
        if isinstance(operator, ast.Gt):
            stop = text
        elif isinstance(operator, ast.GtE):
            stop = f"({text}) - 1"
        else:
            return None
    return stop, dependency


def _shadowed_builtin(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg == name:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) == name:
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            return True
        if isinstance(node, ast.ExceptHandler) and node.name == name:
            return True
    return False


def _body_safe(node: ast.While, counter: str, dependency: str | None) -> bool:
    if not node.body:
        return False
    # The update must be the last *direct* statement of the loop body.
    if _counter_step(node.body[-1]) is None:
        return False

    for statement in node.body[:-1]:
        for descendant in ast.walk(statement):
            if isinstance(descendant, (ast.Continue, ast.Yield, ast.YieldFrom, ast.Await)):
                return False
            if isinstance(descendant, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                return False
            if isinstance(descendant, ast.Name) and isinstance(descendant.ctx, (ast.Store, ast.Del)):
                if descendant.id == counter or descendant.id == dependency:
                    return False
            if isinstance(descendant, (ast.Global, ast.Nonlocal)):
                if counter in descendant.names or dependency in descendant.names:
                    return False
            # A call with the bound object (e.g. items.pop()) can change len().
            if dependency is not None and isinstance(descendant, ast.Call):
                if isinstance(descendant.func, ast.Attribute):
                    if isinstance(descendant.func.value, ast.Name) and descendant.func.value.id == dependency:
                        return False
                for arg in [*descendant.args, *(kw.value for kw in descendant.keywords)]:
                    if any(isinstance(part, ast.Name) and part.id == dependency for part in ast.walk(arg)):
                        if not (isinstance(descendant.func, ast.Name) and descendant.func.id == "print"):
                            return False
    # Python for-else and while-else both run the else suite on normal completion.
    return True


def _header_edit(source: str, node: ast.While, counter: str, stop: str, step: int) -> _Edit | None:
    if node.test.lineno != node.lineno or node.test.end_lineno != node.lineno:
        return None
    lines = source.splitlines(keepends=True)
    if node.lineno > len(lines):
        return None
    line = lines[node.lineno - 1]
    ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    raw = line[:-len(ending)] if ending else line
    indent = raw[:node.col_offset]
    if indent.strip() or not raw[node.col_offset:].startswith("while "):
        return None
    # Locate the real header colon, not a colon inside a string or a comment.
    depth = 0
    colon = None
    try:
        tokens = tokenize.generate_tokens(io.StringIO(raw + "\n").readline)
        for token in tokens:
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
    # Keep the exact existing final increment to preserve the counter's final value.
    range_args = f"{counter}, {stop}" if step == 1 else f"{counter}, {stop}, {step}"
    replacement = f"{indent}for {counter} in range({range_args}):{tail}{ending}"
    start = sum(len(ln.encode("utf-8")) for ln in lines[:node.lineno - 1])
    return _Edit(start, start + len(line.encode("utf-8")), replacement.encode("utf-8"))


def transform_counted_while_to_for(code: str) -> str:
    """Change safely bounded while loops into for loops; never change for loops.

    Supports i += step, i -= step, i = i + step, i = step + i,
    i = i - step; <, <=, >, >=; reversed comparisons; integer literals,
    simple name bounds, len(name), and while-else/break (but not continue).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    if _shadowed_builtin(tree, "range") or _shadowed_builtin(tree, "len"):
        return code

    edits: list[_Edit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.While) or not node.body:
            continue
        update = _counter_step(node.body[-1])
        if update is None:
            continue
        counter, step = update
        if step == 0 or abs(step) > 1000000:
            continue
        check = _condition(node.test, counter, step)
        if check is None:
            continue
        stop, dependency = check
        if not _body_safe(node, counter, dependency):
            continue
        edit = _header_edit(code, node, counter, stop, step)
        if edit is not None:
            edits.append(edit)

    if not edits:
        return code
    result = code.encode("utf-8")
    for edit in sorted(edits, key=lambda item: item.start, reverse=True):
        result = result[:edit.start] + edit.replacement + result[edit.end:]
    try:
        transformed = result.decode("utf-8")
        ast.parse(transformed)
        return transformed
    except (UnicodeDecodeError, SyntaxError):
        return code
