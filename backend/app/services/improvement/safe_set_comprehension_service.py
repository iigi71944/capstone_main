"""Conservative set() + for/add <-> set-comprehension transformations.

The transformer avoids changing variable scopes, comments inside edited spans,
user-call expressions, shadowed builtins, or nontrivial iteration. It is not a
proof of equivalence for arbitrary programs; keep runtime verification enabled.
"""

from __future__ import annotations

import ast
import copy
import tokenize

from app.services.improvement.safe_dict_comprehension_service import (
    _has_dynamic_names, _safe_expression, _range_shadowed, _outside_name,
    _target_names, _statement_blocks, _prepare_edit, _used_names,
    _fresh, _ReplaceNames, _comments,
)


def _set_shadowed(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == 'set' and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg == 'set':
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == 'set':
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) == 'set':
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and 'set' in node.names:
            return True
    return False


def _is_empty_set_call(expr: ast.expr) -> bool:
    return (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id == 'set' and not expr.args and not expr.keywords)


def _extract_add(loop: ast.For, output: str):
    if loop.orelse or loop.type_comment or len(loop.body) != 1:
        return None
    node = loop.body[0]
    filters: list[ast.expr] = []
    while isinstance(node, ast.If):
        if node.orelse or len(node.body) != 1:
            return None
        filters.append(node.test)
        node = node.body[0]
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return None
    call = node.value
    if not (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
            and call.func.value.id == output and call.func.attr == 'add'
            and len(call.args) == 1 and not call.keywords):
        return None
    return call.args[0], filters


def _collapse(tree: ast.AST, first: ast.stmt, second: ast.stmt, allow_range: bool):
    if not (isinstance(first, ast.Assign) and len(first.targets) == 1
            and isinstance(first.targets[0], ast.Name)
            and _is_empty_set_call(first.value) and isinstance(second, ast.For)):
        return None
    output = first.targets[0].id
    names = _target_names(second.target)
    if names is None or output in names:
        return None
    extracted = _extract_add(second, output)
    if extracted is None:
        return None
    value, filters = extracted
    if not _safe_expression(second.iter, allow_range=allow_range):
        return None
    if not all(_safe_expression(expr) for expr in (value, *filters)):
        return None
    if any(n.id == output for expr in (second.iter, value, *filters)
           for n in ast.walk(expr) if isinstance(n, ast.Name)):
        return None
    if any(_outside_name(tree, name, first, second) for name in names):
        return None
    comp = ast.SetComp(
        elt=copy.deepcopy(value),
        generators=[ast.comprehension(
            target=copy.deepcopy(second.target), iter=copy.deepcopy(second.iter),
            ifs=[copy.deepcopy(expr) for expr in filters], is_async=0,
        )],
    )
    return [ast.Assign(targets=[copy.deepcopy(first.targets[0])], value=comp)]


def _expand(stmt: ast.stmt, used: set[str], allow_range: bool):
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.SetComp)
            and len(stmt.value.generators) == 1):
        return None
    comp = stmt.value
    gen = comp.generators[0]
    names = _target_names(gen.target)
    if not names or gen.is_async:
        return None
    if not _safe_expression(gen.iter, allow_range=allow_range):
        return None
    if not all(_safe_expression(expr) for expr in (comp.elt, *gen.ifs)):
        return None
    if any(node.id in names for node in ast.walk(gen.iter) if isinstance(node, ast.Name)):
        return None
    temp_result = _fresh(used, 'set_result')
    rename = {name: _fresh(used, 'set_item') for name in names}
    mapper = _ReplaceNames(rename)
    target = mapper.visit(copy.deepcopy(gen.target))
    elt = mapper.visit(copy.deepcopy(comp.elt))
    filters = [mapper.visit(copy.deepcopy(expr)) for expr in gen.ifs]
    call = ast.Expr(value=ast.Call(
        func=ast.Attribute(value=ast.Name(temp_result, ast.Load()), attr='add', ctx=ast.Load()),
        args=[elt], keywords=[],
    ))
    body: list[ast.stmt] = [call]
    for condition in reversed(filters):
        body = [ast.If(test=condition, body=body, orelse=[])]
    loop = ast.For(target=target, iter=copy.deepcopy(gen.iter), body=body,
                   orelse=[], type_comment=None)
    setup = [ast.Assign(targets=[ast.Name(temp_result, ast.Store())],
                        value=ast.Call(func=ast.Name('set', ast.Load()), args=[], keywords=[]))]
    setup.extend(ast.Assign(targets=[ast.Name(name, ast.Store())], value=ast.Constant(None))
                 for name in rename.values())
    commit = ast.Assign(targets=[copy.deepcopy(stmt.targets[0])],
                        value=ast.Name(temp_result, ast.Load()))
    delete = ast.Delete(targets=[ast.Name(name, ast.Del())
                                 for name in [temp_result, *rename.values()]])
    guarded = ast.Try(body=[loop, commit], handlers=[], orelse=[], finalbody=[delete])
    return [*setup, guarded]


def _rewrite(code: str, direction: str) -> str:
    try:
        tree = ast.parse(code)
        if _has_dynamic_names(tree) or _set_shadowed(tree):
            return code
        comments = _comments(code)
        allow_range = not _range_shadowed(tree)
        used = _used_names(tree)
        edits = []
        for block in _statement_blocks(tree):
            if direction == 'collapse':
                pairs = ((block[i], block[i+1]) for i in range(len(block)-1))
                for first, second in pairs:
                    replacement = _collapse(tree, first, second, allow_range)
                    if replacement is None:
                        continue
                    edit = _prepare_edit(code, first, second, replacement, comments)
                    if edit is not None and not any(e.start < edit.end and edit.start < e.end for e in edits):
                        edits.append(edit)
            else:
                for stmt in block:
                    replacement = _expand(stmt, used, allow_range)
                    if replacement is None:
                        continue
                    edit = _prepare_edit(code, stmt, stmt, replacement, comments)
                    if edit is not None and not any(e.start < edit.end and edit.start < e.end for e in edits):
                        edits.append(edit)
        if not edits:
            return code
        output = code.encode('utf-8')
        for edit in sorted(edits, key=lambda e: e.start, reverse=True):
            output = output[:edit.start] + edit.replacement + output[edit.end:]
        changed = output.decode('utf-8')
        ast.parse(changed)
        return changed
    except (SyntaxError, TypeError, ValueError, RecursionError, UnicodeError, tokenize.TokenError):
        return code


def transform_for_add_to_set_comprehension(code: str) -> str:
    return _rewrite(code, 'collapse')


def transform_set_comprehension_to_for_add(code: str) -> str:
    return _rewrite(code, 'expand')
