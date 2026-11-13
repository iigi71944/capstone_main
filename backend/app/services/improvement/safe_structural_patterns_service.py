"""Conservative, local code-style conversions.

Supported families:
* contextlib.suppress(E) <-> try/except E: pass (only builtin exceptions)
* a local, statically defined function's positional <-> same-order keyword calls
* getattr(obj, 'name') <-> obj.name (when unshadowed)

The goal is readability-oriented syntax rewriting, not arbitrary refactoring.
If a construct involves dynamic bindings, introspection, comments in the
replaced statement, or a scope ambiguity it is intentionally left unchanged.
"""

from __future__ import annotations

import ast
import copy
import keyword
import tokenize

from app.services.improvement.safe_dict_comprehension_service import (
    _comments, _prepare_edit,
)

_EXCEPTION_NAMES = {
    'ValueError', 'TypeError', 'IndexError', 'KeyError',
    'ZeroDivisionError', 'OverflowError', 'LookupError',
}
_SENSITIVE = {'locals', 'globals', 'vars', 'eval', 'exec', 'dir', '__import__',
              'inspect', 'sys', 'setattr', 'delattr', 'compile', 'frame'}


def _is_shadowed(tree: ast.AST, name: str) -> bool:
    """Detect any non-builtin binding to name (including nested scopes)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg == name:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) == name:
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            return True
    return False


def _sensitive(tree: ast.AST) -> bool:
    if any(isinstance(n, (ast.Import, ast.ImportFrom))
           and any(a.name in {"*", "sys", "inspect"} for a in n.names)
           for n in ast.walk(tree)):
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _SENSITIVE:
            return True
        if isinstance(node, ast.Attribute) and node.attr in {
            '__dict__', '__code__', '__class__', '__annotations__', '__globals__',
        }:
            return True
    return False


def _contextlib_import_ok(tree: ast.Module) -> bool:
    imports = [n for n in tree.body if isinstance(n, ast.Import)
               for a in n.names if a.name == 'contextlib' and a.asname is None]
    if len(imports) != 1:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == 'contextlib' and isinstance(node.ctx, (ast.Store, ast.Del)):
            return False
        if isinstance(node, ast.arg) and node.arg == 'contextlib':
            return False
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.name == 'contextlib':
            return False
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split('.')[0]
                if bound == 'contextlib' and not (isinstance(node, ast.Import) and alias.name == 'contextlib' and alias.asname is None):
                    return False
    return True


def _except_type(tree: ast.AST, expr: ast.AST | None) -> ast.Name | None:
    if not isinstance(expr, ast.Name) or expr.id not in _EXCEPTION_NAMES:
        return None
    if _is_shadowed(tree, expr.id):
        return None
    return copy.deepcopy(expr)


def _to_try(tree: ast.Module, stmt: ast.stmt) -> list[ast.stmt] | None:
    if not (isinstance(stmt, ast.With) and len(stmt.items) == 1
            and stmt.items[0].optional_vars is None):
        return None
    call = stmt.items[0].context_expr
    if not (isinstance(call, ast.Call) and not call.keywords and len(call.args) == 1
            and isinstance(call.func, ast.Attribute) and call.func.attr == 'suppress'
            and isinstance(call.func.value, ast.Name) and call.func.value.id == 'contextlib'):
        return None
    exception = _except_type(tree, call.args[0])
    if exception is None:
        return None
    return [ast.Try(body=copy.deepcopy(stmt.body),
                    handlers=[ast.ExceptHandler(type=exception, name=None, body=[ast.Pass()])],
                    orelse=[], finalbody=[])]


def _to_suppress(tree: ast.Module, stmt: ast.stmt) -> list[ast.stmt] | None:
    if not (isinstance(stmt, ast.Try) and len(stmt.handlers) == 1
            and not stmt.orelse and not stmt.finalbody):
        return None
    handler = stmt.handlers[0]
    if not (handler.name is None and len(handler.body) == 1
            and isinstance(handler.body[0], ast.Pass)):
        return None
    exception = _except_type(tree, handler.type)
    if exception is None:
        return None
    call = ast.Call(func=ast.Attribute(value=ast.Name('contextlib', ast.Load()),
                                       attr='suppress', ctx=ast.Load()),
                    args=[exception], keywords=[])
    return [ast.With(items=[ast.withitem(context_expr=call, optional_vars=None)],
                     body=copy.deepcopy(stmt.body), type_comment=None)]


def _plain_signature(stmt: ast.FunctionDef) -> list[str] | None:
    a = stmt.args
    if (stmt.decorator_list or stmt.returns is not None or stmt.type_comment
            or a.posonlyargs or a.vararg or a.kwonlyargs or a.kwarg
            or a.defaults or a.kw_defaults or getattr(stmt, 'type_params', [])):
        return None
    if not a.args or any(arg.annotation is not None for arg in a.args):
        return None
    return [arg.arg for arg in a.args]


def _module_function(tree: ast.Module, name: str, statement_index: int) -> list[str] | None:
    # Only a single top-level function definition and no name rebinding.
    matches = [(i, n) for i, n in enumerate(tree.body)
               if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(matches) != 1 or matches[0][0] >= statement_index:
        return None
    signature = _plain_signature(matches[0][1])
    if signature is None:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
            return None
        if isinstance(node, ast.arg) and node.arg == name:
            return None
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef)) and node.name == name:
            return None
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) == name:
            return None
    parents = {id(child): n for n in ast.walk(tree) for child in ast.iter_child_nodes(n)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load):
            parent = parents.get(id(n))
            if not (isinstance(parent, ast.Call) and parent.func is n):
                return None
    return signature


def _change_call(stmt: ast.stmt, signature: list[str], direction: str) -> list[ast.stmt] | None:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        call = stmt.value
    elif isinstance(stmt, ast.Expr):
        call = stmt.value
    else:
        return None
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
        return None
    if direction == 'to_keywords':
        if call.keywords or len(call.args) != len(signature) or any(isinstance(arg, ast.Starred) for arg in call.args):
            return None
        new_call = ast.Call(func=copy.deepcopy(call.func), args=[], keywords=[
            ast.keyword(arg=param, value=copy.deepcopy(arg)) for param, arg in zip(signature, call.args)
        ])
    else:
        if (call.args or len(call.keywords) != len(signature)
                or [k.arg for k in call.keywords] != signature):
            return None
        new_call = ast.Call(func=copy.deepcopy(call.func),
                            args=[copy.deepcopy(k.value) for k in call.keywords], keywords=[])
    updated = copy.deepcopy(stmt)
    if isinstance(updated, ast.Expr):
        updated.value = new_call
    else:
        updated.value = new_call
    return [updated]


def _convert_attribute(tree: ast.Module, stmt: ast.stmt, direction: str) -> list[ast.stmt] | None:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        expression = stmt.value
    elif isinstance(stmt, ast.Expr):
        expression = stmt.value
    else:
        return None
    if direction == 'to_attribute':
        if not (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name)
                and expression.func.id == 'getattr' and len(expression.args) == 2
                and not expression.keywords and isinstance(expression.args[0], ast.Name)
                and isinstance(expression.args[1], ast.Constant)
                and isinstance(expression.args[1].value, str)):
            return None
        attr = expression.args[1].value
        if (not attr.isidentifier() or keyword.iskeyword(attr)
                or attr.startswith('__') or _is_shadowed(tree, 'getattr')):
            return None
        new_expr = ast.Attribute(value=copy.deepcopy(expression.args[0]), attr=attr, ctx=ast.Load())
    else:
        if not (isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name)
                and not expression.attr.startswith('__') and not _is_shadowed(tree, 'getattr')):
            return None
        new_expr = ast.Call(func=ast.Name('getattr', ast.Load()),
                            args=[copy.deepcopy(expression.value), ast.Constant(expression.attr)], keywords=[])
    updated = copy.deepcopy(stmt)
    updated.value = new_expr
    return [updated]


def _rewrite(code: str, direction: str) -> str:
    try:
        tree = ast.parse(code)
        if _sensitive(tree):
            return code
        comments = _comments(code)
        edits = []
        if direction in ('to_try', 'to_suppress') and not _contextlib_import_ok(tree):
            return code
        for i, stmt in enumerate(tree.body):
            # The suppress module must already be imported at this point;
            # an import that occurs later is not sufficient at runtime.
            if direction in ('to_try', 'to_suppress'):
                if not any(isinstance(prior, ast.Import)
                           and any(a.name == 'contextlib' and a.asname is None
                                   for a in prior.names)
                           for prior in tree.body[:i]):
                    continue
            replacements = None
            if direction == 'to_try':
                replacements = _to_try(tree, stmt)
            elif direction == 'to_suppress':
                replacements = _to_suppress(tree, stmt)
            elif direction in ('to_keywords', 'to_positional'):
                if isinstance(stmt, (ast.Assign, ast.Expr)):
                    call = stmt.value
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                        signature = _module_function(tree, call.func.id, i)
                        if signature is not None:
                            replacements = _change_call(stmt, signature, direction)
            elif direction in ('to_attribute', 'to_getattr'):
                replacements = _convert_attribute(tree, stmt, direction)
            if replacements:
                edit = _prepare_edit(code, stmt, stmt, replacements, comments)
                if edit is not None:
                    edits.append(edit)
        if not edits:
            return code
        output = code.encode('utf-8')
        for e in sorted(edits, key=lambda edit: edit.start, reverse=True):
            output = output[:e.start] + e.replacement + output[e.end:]
        new = output.decode('utf-8')
        ast.parse(new)
        return new
    except (SyntaxError, TypeError, ValueError, RecursionError, UnicodeError, tokenize.TokenError):
        return code


def transform_suppress_to_try(code: str) -> str:
    return _rewrite(code, 'to_try')


def transform_try_to_suppress(code: str) -> str:
    return _rewrite(code, 'to_suppress')


def transform_positional_to_keyword_call(code: str) -> str:
    return _rewrite(code, 'to_keywords')


def transform_keyword_to_positional_call(code: str) -> str:
    return _rewrite(code, 'to_positional')


def transform_getattr_to_attribute(code: str) -> str:
    return _rewrite(code, 'to_attribute')


def transform_attribute_to_getattr(code: str) -> str:
    return _rewrite(code, 'to_getattr')
