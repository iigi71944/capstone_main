"""Conservative list-comprehension <-> for/append transformations.

This is a standalone service.  It never changes existing project modules and is
not automatically registered with the saved-style action dispatcher.

The accepted subset is purposefully narrow: one synchronous generator, name or
unpacking targets, no assignment expressions, closures, introspection, comments
inside rewritten spans or complex control flow. Unsupported source is returned
unchanged. It does not promise equivalence for dynamically instrumented code.
"""

from __future__ import annotations

import ast
import copy
import io
import tokenize
from dataclasses import dataclass


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes


_DANGEROUS = {"locals", "globals", "vars", "dir", "eval", "exec", "compile", "__import__", "sys", "inspect"}
_COMPLEX = (ast.Lambda, ast.NamedExpr, ast.Yield, ast.YieldFrom, ast.Await,
            ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp)


def _safe_syntax(node: ast.AST, allow_range: bool = False) -> bool:
    for child in ast.walk(node):
        if isinstance(child, _COMPLEX):
            return False
        if isinstance(child, ast.Name) and child.id in _DANGEROUS:
            return False
        if isinstance(child, ast.Call):
            # The unshadowed built-in range() is a useful exception.
            # Other calls can inspect their caller / mutate state.
            if not (allow_range and isinstance(child.func, ast.Name)
                    and child.func.id == "range" and not child.keywords
                    and all(isinstance(arg, ast.Constant) and type(arg.value) is int for arg in child.args)
                    and len(child.args) in (1, 2, 3)):
                return False
    return True


def _names_in_target(target: ast.expr) -> tuple[str, ...] | None:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, (ast.Tuple, ast.List)) and target.elts:
        names: list[str] = []
        for elt in target.elts:
            found = _names_in_target(elt)
            if found is None:
                return None
            names.extend(found)
        if len(names) == len(set(names)):
            return tuple(names)
    return None


def _has_dynamic_names(tree: ast.AST) -> bool:
    for child in ast.walk(tree):
        if isinstance(child, ast.Name) and child.id in _DANGEROUS:
            return True
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            for alias in child.names:
                if alias.name in {"*", "inspect", "sys"}:
                    return True
    return False


def _range_shadowed(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "range" and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg == "range":
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == "range":
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.', 1)[0]) == "range":
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and "range" in node.names:
            return True
    return False


def _comments(source: str) -> set[int]:
    return {token.start[0] for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type == tokenize.COMMENT}


def _blocks(tree: ast.AST):
    for parent in ast.walk(tree):
        for _, value in ast.iter_fields(parent):
            if isinstance(value, list) and value and all(isinstance(x, ast.stmt) for x in value):
                yield value


def _span(source: str, first: ast.stmt, last: ast.stmt) -> tuple[int, int, str, str] | None:
    lines = source.splitlines(keepends=True)
    if not (first.end_lineno and last.end_lineno and last.end_col_offset is not None):
        return None
    if first.lineno > len(lines) or last.end_lineno > len(lines):
        return None
    prefix = lines[first.lineno - 1].encode('utf-8')[:first.col_offset]
    suffix = lines[last.end_lineno - 1].encode('utf-8')[last.end_col_offset:]
    if prefix.strip() or suffix.strip():
        return None
    try:
        indent = prefix.decode('utf-8')
    except UnicodeError:
        return None
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode('utf-8')))
    newline = '\r\n' if '\r\n' in source else '\n'
    return (offsets[first.lineno-1]+first.col_offset,
            offsets[last.end_lineno-1]+last.end_col_offset, indent, newline)


def _edit(source: str, first: ast.stmt, last: ast.stmt, statements: list[ast.stmt],
          commented: set[int]) -> _Edit | None:
    if any(first.lineno <= line <= last.end_lineno for line in commented):
        return None
    span = _span(source, first, last)
    if span is None:
        return None
    start, end, indent, newline = span
    module = ast.fix_missing_locations(ast.Module(body=statements, type_ignores=[]))
    output = ast.unparse(module)
    replacement = (newline + indent).join(output.split('\n'))
    return _Edit(start, end, replacement.encode('utf-8'))


def _get_append(loop: ast.For, name: str) -> tuple[ast.expr, list[ast.expr]] | None:
    if loop.orelse or len(loop.body) != 1:
        return None
    statement = loop.body[0]
    filters: list[ast.expr] = []
    while isinstance(statement, ast.If):
        if statement.orelse or len(statement.body) != 1:
            return None
        filters.append(statement.test)
        statement = statement.body[0]
    if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)):
        return None
    call = statement.value
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == 'append'
            and isinstance(call.func.value, ast.Name) and call.func.value.id == name
            and len(call.args) == 1 and not call.keywords):
        return None
    return call.args[0], filters


def _name_outside_group(tree: ast.AST, name: str, first: ast.stmt, last: ast.stmt) -> bool:
    for item in ast.walk(tree):
        if isinstance(item, ast.Name) and item.id == name:
            # Includes uses in later code; changing the for-target final binding
            # would be observable, so skip unless confined to the pair.
            if item.lineno < first.lineno or item.lineno > last.end_lineno:
                return True
    return False


def _used_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(tree):
        if isinstance(item, ast.Name):
            names.add(item.id)
        elif isinstance(item, ast.arg):
            names.add(item.arg)
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(item.name)
        elif isinstance(item, ast.alias):
            names.add(item.asname or item.name.split('.', 1)[0])
        elif isinstance(item, (ast.Global, ast.Nonlocal)):
            names.update(item.names)
    return names


def _fresh(used: set[str], stem: str) -> str:
    i = 0
    while True:
        candidate = f'__capstone_{stem}_{i}'
        if candidate not in used:
            used.add(candidate)
            return candidate
        i += 1


class _Rename(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name):
        if node.id in self.mapping:
            return ast.copy_location(ast.Name(self.mapping[node.id], copy.deepcopy(node.ctx)), node)
        return node


def _collapse_pair(tree: ast.AST, first: ast.stmt, second: ast.stmt) -> list[ast.stmt] | None:
    if not (isinstance(first, ast.Assign) and len(first.targets) == 1
            and isinstance(first.targets[0], ast.Name)
            and isinstance(first.value, ast.List) and not first.value.elts
            and isinstance(second, ast.For)):
        return None
    result = first.targets[0].id
    targets = _names_in_target(second.target)
    if not targets or result in targets:
        return None
    extracted = _get_append(second, result)
    if extracted is None:
        return None
    elt, filters = extracted
    if not _safe_syntax(second.iter, allow_range=not _range_shadowed(tree)):
        return None
    if not all(_safe_syntax(x) for x in (elt, *filters)):
        return None
    if any(isinstance(x, ast.Name) and x.id == result
           for node in (second.iter, elt, *filters) for x in ast.walk(node)):
        return None
    if any(_name_outside_group(tree, name, first, second) for name in targets):
        return None
    gen = ast.comprehension(target=copy.deepcopy(second.target),
                            iter=copy.deepcopy(second.iter),
                            ifs=[copy.deepcopy(x) for x in filters], is_async=0)
    expr = ast.ListComp(elt=copy.deepcopy(elt), generators=[gen])
    return [ast.Assign(targets=[copy.deepcopy(first.targets[0])], value=expr)]


def _expand_assign(stmt: ast.stmt, used: set[str], allow_range: bool) -> list[ast.stmt] | None:
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.ListComp) and len(stmt.value.generators) == 1):
        return None
    comp = stmt.value
    gen = comp.generators[0]
    original_names = _names_in_target(gen.target)
    if not original_names or gen.is_async:
        return None
    if not _safe_syntax(gen.iter, allow_range=allow_range):
        return None
    if not all(_safe_syntax(x) for x in (comp.elt, *gen.ifs)):
        return None
    # All generated names are unique to the full module, including imported and
    # function/class definitions.  Cleanup happens even on exceptions.
    temp_result = _fresh(used, 'list_result')
    mapping = {name: _fresh(used, 'list_item') for name in original_names}
    renamer = _Rename(mapping)
    renamed_target = renamer.visit(copy.deepcopy(gen.target))
    renamed_value = renamer.visit(copy.deepcopy(comp.elt))
    renamed_filters = [renamer.visit(copy.deepcopy(x)) for x in gen.ifs]
    append = ast.Expr(ast.Call(func=ast.Attribute(value=ast.Name(temp_result, ast.Load()),
                                                  attr='append', ctx=ast.Load()),
                               args=[renamed_value], keywords=[]))
    body: list[ast.stmt] = [append]
    for cond in reversed(renamed_filters):
        body = [ast.If(test=cond, body=body, orelse=[])]
    # Do not rename gen.iter: the first iterator is evaluated in the enclosing scope.
    loop = ast.For(target=renamed_target, iter=copy.deepcopy(gen.iter), body=body,
                   orelse=[], type_comment=None)
    init = [ast.Assign([ast.Name(temp_result, ast.Store())], ast.List([], ast.Load()))]
    init.extend(ast.Assign([ast.Name(name, ast.Store())], ast.Constant(None))
                for name in mapping.values())
    assignment = ast.Assign(targets=[copy.deepcopy(stmt.targets[0])],
                            value=ast.Name(temp_result, ast.Load()))
    cleanup = ast.Delete(targets=[ast.Name(name, ast.Del())
                                  for name in (temp_result, *mapping.values())])
    guard = ast.Try(body=[loop, assignment], handlers=[], orelse=[], finalbody=[cleanup])
    return [*init, guard]


def _rewrite(code: str, direction: str) -> str:
    try:
        tree = ast.parse(code)
        if _has_dynamic_names(tree):
            return code
        comments = _comments(code)
        edits: list[_Edit] = []
        used = _used_names(tree)
        for block in _blocks(tree):
            if direction == 'collapse':
                for index in range(len(block)-1):
                    first, second = block[index:index+2]
                    lowered = _collapse_pair(tree, first, second)
                    if lowered is None:
                        continue
                    edit = _edit(code, first, second, lowered, comments)
                    if edit is not None and not any(edit.start < x.end and x.start < edit.end for x in edits):
                        edits.append(edit)
            elif direction == 'expand':
                for stmt in block:
                    # _expand_assign mutates its `used` only for a candidate;
                    # choose unique names globally for all accepted edits.
                    if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.ListComp)):
                        continue
                    candidate = _expand_assign(stmt, used, not _range_shadowed(tree))
                    if candidate is None:
                        continue
                    edit = _edit(code, stmt, stmt, candidate, comments)
                    if edit is not None and not any(edit.start < x.end and x.start < edit.end for x in edits):
                        edits.append(edit)
            else:
                raise ValueError('unknown direction')
        if not edits:
            return code
        output = code.encode('utf-8')
        for edit in sorted(edits, key=lambda x: x.start, reverse=True):
            output = output[:edit.start] + edit.replacement + output[edit.end:]
        text = output.decode('utf-8')
        ast.parse(text)
        return text
    except (SyntaxError, ValueError, UnicodeError, tokenize.TokenError, TypeError, RecursionError):
        return code


def transform_for_append_to_list_comprehension(code: str) -> str:
    """Collapse safe two-statement list-building loops into a comprehension."""
    return _rewrite(code, 'collapse')


def transform_list_comprehension_to_for_append(code: str) -> str:
    """Expand supported list comprehensions into guarded, explicit for-loops."""
    return _rewrite(code, 'expand')
