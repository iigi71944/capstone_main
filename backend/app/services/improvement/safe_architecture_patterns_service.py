"""Narrow architecture-oriented code transforms (batch 4).

These are *not* general refactoring engines. They recognize deliberately
restricted source patterns; anything outside the proven patterns is unchanged.
No input code is executed. Original whitespace/comments outside a transformed
statement are preserved. Tracebacks, reflection and dynamic namespaces are
not claimed to be equivalent; such sensitive uses are rejected conservatively.
"""
from __future__ import annotations

import ast
import copy

from app.services.improvement.safe_dict_comprehension_service import _comments, _prepare_edit, _used_names
from app.services.improvement.safe_remaining_patterns_service import _safe_to_read, _rewrite_edits, _Edit
from app.services.improvement.safe_structural_patterns_service import _is_shadowed

_ALLOWED_MATH_FUNCS = frozenset({'sqrt', 'floor', 'ceil', 'fabs', 'sin', 'cos', 'tan'})
_ALLOWED_EXCEPTIONS = frozenset({'ValueError', 'TypeError'})
_ALLOWED_COMPARE = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
_ALLOWED_ARITHMETIC = (ast.Add, ast.Sub, ast.Mult)


def _edit(code: str, first: ast.stmt, last: ast.stmt, replacement: list[ast.stmt], comments: set[int]):
    edit = _prepare_edit(code, first, last, replacement, comments)
    return None if edit is None else _Edit(edit.start, edit.end, edit.replacement)


def _pure_expr(node: ast.AST, parameter: str) -> bool:
    """No calls/attributes/subscripts: pure integer-like math and literals only."""
    if isinstance(node, ast.Name):
        return node.id == parameter and isinstance(node.ctx, ast.Load)
    if isinstance(node, ast.Constant):
        return type(node.value) in (int, float, str, bool, type(None))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _pure_expr(node.operand, parameter)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_ARITHMETIC):
        return _pure_expr(node.left, parameter) and _pure_expr(node.right, parameter)
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        return isinstance(node.ops[0], _ALLOWED_COMPARE) and _pure_expr(node.left, parameter) and _pure_expr(node.comparators[0], parameter)
    return False


def _validation_guard(first: ast.stmt, parameter: str) -> bool:
    if not (isinstance(first, ast.If) and len(first.body) == 1 and not first.orelse
            and isinstance(first.body[0], ast.Raise) and first.body[0].cause is None):
        return False
    statement = first.body[0]
    call = statement.exc
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id in _ALLOWED_EXCEPTIONS and len(call.args) == 1
            and not call.keywords and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)):
        return False
    return _pure_expr(first.test, parameter)


def _plain_one_arg_function(stmt: ast.FunctionDef) -> str | None:
    args = stmt.args
    if (stmt.decorator_list or stmt.returns or stmt.type_comment
            or getattr(stmt, 'type_params', ()) or args.posonlyargs or args.kwonlyargs
            or args.vararg or args.kwarg or args.defaults or args.kw_defaults
            or len(args.args) != 1 or args.args[0].annotation is not None):
        return None
    return args.args[0].arg


def transform_extract_validation_helper(code: str) -> str:
    """Simple validation guard + return -> a nested validation helper.

    Only top-level undecorated one-argument functions are eligible. The
    function's callable name, signature, return and raised exception remain.
    """
    prepared = _safe_to_read(code)
    if prepared is None:
        return code
    tree, comments = prepared
    if any(_is_shadowed(tree, name) for name in _ALLOWED_EXCEPTIONS):
        return code
    used = _used_names(tree)
    edits = []
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or len(fn.body) != 2:
            continue
        parameter = _plain_one_arg_function(fn)
        if (parameter is None or not _validation_guard(fn.body[0], parameter)
                or not isinstance(fn.body[1], ast.Return)
                or fn.body[1].value is None
                or not _pure_expr(fn.body[1].value, parameter)):
            continue
        # Avoid name/parameter clashes and introspection-sensitive modules.
        helper = f'__capstone_validate_{parameter}'
        count = 1
        while helper in used:
            helper = f'__capstone_validate_{parameter}_{count}'
            count += 1
        used.add(helper)
        helper_def = ast.FunctionDef(
            name=helper,
            args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=parameter)],
                               vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
            body=[copy.deepcopy(fn.body[0])], decorator_list=[], returns=None, type_comment=None,
        )
        call = ast.Expr(value=ast.Call(func=ast.Name(helper, ast.Load()),
                                       args=[ast.Name(parameter, ast.Load())], keywords=[]))
        new_fn = copy.deepcopy(fn)
        new_fn.body = [helper_def, call, copy.deepcopy(fn.body[1])]
        edit = _edit(code, fn, fn, [new_fn], comments)
        if edit:
            edits.append(edit)
    return _rewrite_edits(code, edits)


def transform_inline_validation_helper(code: str) -> str:
    """Reverse exact local helper template only; unrelated helpers untouched."""
    prepared = _safe_to_read(code)
    if prepared is None:
        return code
    tree, comments = prepared
    edits = []
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or len(fn.body) != 3:
            continue
        parameter = _plain_one_arg_function(fn)
        helper, invocation, final = fn.body
        if (parameter is None or not isinstance(helper, ast.FunctionDef)
                or not helper.name.startswith(f'__capstone_validate_{parameter}')
                or helper.decorator_list or len(helper.body) != 1
                or not _validation_guard(helper.body[0], parameter)
                or _plain_one_arg_function(helper) != parameter
                or not isinstance(invocation, ast.Expr) or not isinstance(invocation.value, ast.Call)
                or not isinstance(invocation.value.func, ast.Name)
                or invocation.value.func.id != helper.name or invocation.value.keywords
                or len(invocation.value.args) != 1 or not isinstance(invocation.value.args[0], ast.Name)
                or invocation.value.args[0].id != parameter
                or not isinstance(final, ast.Return) or final.value is None
                or not _pure_expr(final.value, parameter)):
            continue
        new_fn = copy.deepcopy(fn)
        new_fn.body = [copy.deepcopy(helper.body[0]), copy.deepcopy(final)]
        edit = _edit(code, fn, fn, [new_fn], comments)
        if edit:
            edits.append(edit)
    return _rewrite_edits(code, edits)


def _math_function_pair(stmt: ast.FunctionDef, forward: bool):
    """Local `from math import f` + `return f(x)` <-> `import math` + `return math.f(x)`."""
    if not isinstance(stmt, ast.FunctionDef) or stmt.decorator_list or len(stmt.body) != 2:
        return None
    imp, ret = stmt.body
    if not (isinstance(ret, ast.Return) and isinstance(ret.value, ast.Call)
            and not ret.value.keywords and len(ret.value.args) == 1
            and isinstance(ret.value.args[0], (ast.Name, ast.Constant))):
        return None
    call = ret.value
    if forward:
        if not (isinstance(imp, ast.ImportFrom) and imp.level == 0 and imp.module == 'math'
                and len(imp.names) == 1 and imp.names[0].asname is None
                and imp.names[0].name in _ALLOWED_MATH_FUNCS
                and isinstance(call.func, ast.Name) and call.func.id == imp.names[0].name):
            return None
        method = imp.names[0].name
        updated_import = ast.Import(names=[ast.alias(name='math')])
        new_func = ast.Attribute(value=ast.Name('math', ast.Load()), attr=method, ctx=ast.Load())
    else:
        if not (isinstance(imp, ast.Import) and len(imp.names) == 1
                and imp.names[0].name == 'math' and imp.names[0].asname is None
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name) and call.func.value.id == 'math'
                and call.func.attr in _ALLOWED_MATH_FUNCS):
            return None
        method = call.func.attr
        updated_import = ast.ImportFrom(module='math', names=[ast.alias(name=method)], level=0)
        new_func = ast.Name(method, ast.Load())
    argnames = {n.arg for n in ast.walk(stmt) if isinstance(n, ast.arg)}
    # Replacing an import changes the locally bound name. That name must
    # not appear as the argument (or be a parameter), or the call could
    # change from TypeError to NameError, or use a different value.
    argument = call.args[0]
    if isinstance(argument, ast.Name) and argument.id in {'math', method}:
        return None
    if 'math' in argnames or method in argnames:
        return None
    new_stmt = copy.deepcopy(stmt)
    new_stmt.body[0] = updated_import
    new_stmt.body[1].value.func = new_func
    return new_stmt


def _transform_math_import(code: str, forward: bool) -> str:
    prepared = _safe_to_read(code)
    if prepared is None:
        return code
    tree, comments = prepared
    # Every candidate must be the module's only import; names cannot be
    # dynamically rebound. The import *inside* the matched function is allowed.
    edits = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.FunctionDef):
            continue
        replacement = _math_function_pair(stmt, forward)
        if replacement is None:
            continue
        original_import = stmt.body[0]
        if any(n is not original_import and isinstance(n, (ast.Import, ast.ImportFrom))
               for n in ast.walk(tree)):
            continue
        # math / imported function must not be rebound by outer code.
        if any(isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))
               and n.id in {'math', *list(_ALLOWED_MATH_FUNCS)} for n in ast.walk(tree)):
            continue
        edit = _edit(code, stmt, stmt, [replacement], comments)
        if edit:
            edits.append(edit)
    return _rewrite_edits(code, edits)


def transform_from_math_to_module(code: str) -> str:
    return _transform_math_import(code, True)


def transform_math_module_to_from(code: str) -> str:
    return _transform_math_import(code, False)


def _factory_fields(expr: ast.Call, klass: str, methods: bool) -> list[ast.stmt] | None:
    if not (isinstance(expr.func, ast.Name) and expr.func.id == 'type'
            and not expr.keywords and len(expr.args) == 3
            and isinstance(expr.args[0], ast.Constant) and expr.args[0].value == klass
            and isinstance(expr.args[1], ast.Tuple) and not expr.args[1].elts
            and isinstance(expr.args[2], ast.Dict) and expr.args[2].keys):
        return None
    members = []
    has_method = False
    for key, value in zip(expr.args[2].keys, expr.args[2].values):
        if not (isinstance(key, ast.Constant) and type(key.value) is str
                and key.value.isidentifier() and not key.value.startswith('_')
                and key.value not in ('__doc__', '__module__', '__qualname__', '__annotations__')):
            return None
        if isinstance(value, ast.Constant) and type(value.value) in (int, str, bool, float, type(None)):
            pass
        elif (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
              and value.func.id == 'staticmethod' and not value.keywords
              and len(value.args) == 1 and isinstance(value.args[0], ast.Name)):
            has_method = True
        else:
            return None
        members.append(ast.Assign(targets=[ast.Name(key.value, ast.Store())], value=copy.deepcopy(value)))
    if methods != has_method:
        return None
    return members


def _module_static_function_names(tree: ast.Module) -> set[str]:
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.decorator_list}


def _transform_type_factory(code: str, methods: bool) -> str:
    prepared = _safe_to_read(code)
    if prepared is None:
        return code
    tree, comments = prepared
    if _is_shadowed(tree, 'type') or _is_shadowed(tree, 'staticmethod'):
        return code
    available = _module_static_function_names(tree)
    edits = []
    for i, stmt in enumerate(tree.body):
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Call)):
            continue
        klass = stmt.targets[0].id
        fields = _factory_fields(stmt.value, klass, methods)
        if fields is None:
            continue
        # Rebinding/nested binding and super-dynamic class inspection are unsafe.
        if sum(isinstance(n, ast.Name) and n.id == klass and isinstance(n.ctx, ast.Store)
               for n in ast.walk(tree)) != 1:
            continue
        callnames = [n.value.args[0].id for n in fields if isinstance(n.value, ast.Call)]
        if any(name not in available or not any(isinstance(prev, ast.FunctionDef) and prev.name == name
                                                 for prev in tree.body[:i])
               for name in callnames):
            continue
        if any(isinstance(n, ast.Name) and n.id in callnames and isinstance(n.ctx, (ast.Store, ast.Del))
               for n in ast.walk(tree)):
            continue
        new_class = ast.ClassDef(name=klass, bases=[], keywords=[], body=fields, decorator_list=[])
        edit = _edit(code, stmt, stmt, [new_class], comments)
        if edit:
            edits.append(edit)
    return _rewrite_edits(code, edits)


def transform_type_to_class(code: str) -> str:
    """Static class-only type('Name', (), {'field': literal}) -> class Name."""
    return _transform_type_factory(code, methods=False)


def transform_type_to_class_with_methods(code: str) -> str:
    """Factory staticmethod members -> class statement, preserving top-level function."""
    return _transform_type_factory(code, methods=True)
