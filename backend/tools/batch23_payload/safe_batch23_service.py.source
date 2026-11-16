"""Batch 23: tightly scoped break/global style transformations.

Both edits operate on recognized single-module constructs and preserve original
text around the edit. They do not execute user-supplied Python. They are not
proofs of semantic equivalence under tracing, introspection or metaprogramming.
"""
from __future__ import annotations

import ast
import re

MAX_CHARS = 250_000
_EOL_RE = re.compile(r"(\r\n|\n)$")
_ALLOWED_TEST = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.NotEq)
_FORBIDDEN_DYNAMIC = {"globals", "locals", "vars", "exec", "eval", "compile", "__import__"}


def _parse(code: str):
    if not isinstance(code, str) or not code or len(code) > MAX_CHARS:
        return None
    try:
        tree = ast.parse(code)
    except (SyntaxError, TypeError, ValueError, UnicodeError, RecursionError, MemoryError):
        return None
    # Refuse code that performs dynamic namespace or source inspection.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_DYNAMIC:
                return None
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await)):
            # This batch intentionally handles only ordinary non-dynamic sources.
            return None
    return tree


def _line_eol(line: str):
    matched = _EOL_RE.search(line)
    return matched.group(1) if matched else ''


def _finish(code: str, lines: list[str]):
    result = ''.join(lines)
    try:
        ast.parse(result)
    except (SyntaxError, ValueError, UnicodeError, RecursionError, MemoryError):
        return code
    return result


def _pure_counted_test(node: ast.AST, index: str) -> bool:
    return (isinstance(node, ast.Compare)
            and len(node.ops) == len(node.comparators) == 1
            and isinstance(node.ops[0], _ALLOWED_TEST)
            and isinstance(node.left, ast.Name) and node.left.id == index
            and isinstance(node.comparators[0], ast.Constant)
            and type(node.comparators[0].value) is int)


def _eligible_while(node: ast.While, previous: ast.stmt, code: str, lines: list[str]) -> bool:
    # Only a module-level integer counting loop with exactly one explicit
    # increment/decrement and no else, break or continue is eligible.
    if node.orelse or not node.body or not isinstance(previous, ast.Assign):
        return False
    if len(previous.targets) != 1 or not isinstance(previous.targets[0], ast.Name):
        return False
    index = previous.targets[0].id
    if not (isinstance(previous.value, ast.Constant) and type(previous.value.value) is int
            and _pure_counted_test(node.test, index)):
        return False
    if node.end_lineno is None or node.lineno == node.end_lineno:
        return False
    if any(child is not node and isinstance(child, (ast.Break, ast.Continue, ast.Yield, ast.YieldFrom, ast.Await,
                                                    ast.For, ast.While, ast.AsyncFor, ast.Try, ast.With))
           for child in ast.walk(node)):
        return False
    updates = [statement for statement in node.body
               if isinstance(statement, ast.AugAssign)
               and isinstance(statement.target, ast.Name)
               and statement.target.id == index
               and isinstance(statement.op, (ast.Add, ast.Sub))
               and isinstance(statement.value, ast.Constant)
               and type(statement.value.value) is int
               and statement.value.value > 0]
    if len(updates) != 1:
        return False
    if any(isinstance(child, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
           and any(isinstance(name, ast.Name) and name.id == index
                   and isinstance(name.ctx, ast.Store) for name in ast.walk(child))
           for child in ast.walk(node)):
        return False
    if any(isinstance(child, ast.AugAssign) and child is not updates[0]
           and isinstance(child.target, ast.Name) and child.target.id == index
           for child in ast.walk(node)):
        return False
    # Require flat statements: no alternate paths that omit the update.
    if any(isinstance(statement, (ast.If, ast.Match, ast.FunctionDef, ast.ClassDef,
                                  ast.Return, ast.Raise, ast.Delete))
           for statement in node.body):
        return False
    header = lines[node.lineno - 1]
    condition = ast.get_source_segment(code, node.test)
    if not condition or '\n' in condition or '\r' in condition:
        return False
    eol = _line_eol(header)
    if not eol or header != f'while {condition}:{eol}':
        return False
    if any('\t' in line for line in lines[node.lineno - 1:node.end_lineno]):
        return False
    if any(line.strip() and not line.startswith('    ')
           for line in lines[node.lineno:node.end_lineno]):
        return False
    # Disallow trailing comments whose visual loop attachment would change.
    cursor = node.end_lineno
    while cursor < len(lines) and (not lines[cursor].strip() or lines[cursor].lstrip().startswith('#')):
        if lines[cursor].strip().startswith('#') and lines[cursor].startswith('    '):
            return False
        cursor += 1
    return True


def transform_safe_counted_while_to_guard_break(code: str) -> str:
    """For safe top-level counted loops, introduce a top-of-loop break guard."""
    tree = _parse(code)
    if tree is None:
        return code
    lines = code.splitlines(keepends=True)
    edits: list[tuple[int, int, list[str]]] = []
    for pos, stmt in enumerate(tree.body):
        if not isinstance(stmt, ast.While) or pos == 0:
            continue
        previous = tree.body[pos - 1]
        if not _eligible_while(stmt, previous, code, lines):
            continue
        eol = _line_eol(lines[stmt.lineno - 1])
        condition = ast.get_source_segment(code, stmt.test)
        # Original loop-body indentation stays unchanged: the guard is a sibling.
        body = lines[stmt.lineno:stmt.end_lineno]
        replacement = [f'while True:{eol}', f'    if not ({condition}):{eol}',
                       f'        break{eol}', *body]
        edits.append((stmt.lineno - 1, stmt.end_lineno, replacement))
    if not edits:
        return code
    for start, end, replacement in reversed(edits):
        lines[start:end] = replacement
    return _finish(code, lines)


def transform_safe_readonly_global_declaration(code: str) -> str:
    """Insert a redundant explicit global for a trivial read-only function.

    Only module-level `def f(): return name` and a module-level primitive
    literal binding for `name` are eligible. The function reads the same global
    value before and after the edit; no parameters, closure, or stores exist.
    """
    tree = _parse(code)
    if tree is None:
        return code
    lines = code.splitlines(keepends=True)
    bindings = {
        stmt.targets[0].id
        for stmt in tree.body
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and isinstance(stmt.value, ast.Constant)
        and type(stmt.value.value) in (str, int, bool, float, type(None))
    }
    edits: list[tuple[int, str]] = []
    for stmt in tree.body:
        if not (isinstance(stmt, ast.FunctionDef) and not stmt.decorator_list
                and len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Return)
                and isinstance(stmt.body[0].value, ast.Name)
                and not stmt.args.posonlyargs and not stmt.args.args
                and not stmt.args.kwonlyargs and stmt.args.vararg is None
                and stmt.args.kwarg is None and not stmt.args.defaults
                and not stmt.args.kw_defaults and not stmt.returns):
            continue
        name = stmt.body[0].value.id
        if name not in bindings or name == stmt.name:
            continue
        if not (stmt.end_lineno == stmt.lineno + 1
                and lines[stmt.lineno - 1] in (f'def {stmt.name}():\n', f'def {stmt.name}():\r\n')):
            continue
        return_line = lines[stmt.lineno]
        ending = _line_eol(lines[stmt.lineno - 1])
        if return_line.rstrip('\r\n') != f'    return {name}':
            continue
        edits.append((stmt.lineno, f'    global {name}{ending}'))
    if not edits:
        return code
    for index, new_line in reversed(edits):
        lines.insert(index, new_line)
    return _finish(code, lines)
