"""Batch 31: seven constrained, executable style transformations.

These are intentionally tiny *closed-module* rewrites. General-purpose Python
signature changes, asynchronous scheduling changes and long-function inlining
are not safe without whole-program analysis. Refuse everything outside the
explicit, self-contained patterns below. Legacy runtime rollback still applies.
"""
from __future__ import annotations

import ast

MAX_CHARS = 40_000
_ALLOWED = (int, float, str, bool)


def _canonical(code: str):
    if not isinstance(code, str) or not code or len(code) > MAX_CHARS:
        return None
    if '\r' in code.replace('\r\n', ''):
        return None
    normal = code.replace('\r\n', '\n')
    try:
        tree = ast.parse(normal)
        # Canonical exact-match excludes comments, multiline expressions,
        # decorators, opaque formatting and syntax with inspectable side effects.
        if normal.rstrip('\n') not in {ast.unparse(tree), ast.unparse(tree).replace('\n\n', '\n')}:
            return None
    except (SyntaxError, UnicodeError, ValueError, RecursionError, MemoryError):
        return None
    return tree, '\r\n' if '\r\n' in code else '\n', code.endswith(('\n', '\r\n'))


def _finish(lines: list[str], eol: str, final_newline: bool) -> str:
    text = eol.join(lines) + (eol if final_newline else '')
    try:
        ast.parse(text)
    except (SyntaxError, UnicodeError, ValueError, RecursionError, MemoryError):
        raise ValueError('unsafe output')
    return text


def _primitive(node):
    return isinstance(node, ast.Constant) and type(node.value) in _ALLOWED


def _pure_literal_expression(node):
    """Only primitive constant arithmetic, without calls or name lookup."""
    if _primitive(node):
        return True
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
        return False
    if not (_primitive(node.left) and _primitive(node.right)):
        return False
    left, right = node.left.value, node.right.value
    if type(left) is not type(right):
        return False
    if isinstance(node.op, ast.Add):
        return type(left) in (int, float, str)
    return type(left) in (int, float)


def _private_fn(node, asynchronous=False):
    klass = ast.AsyncFunctionDef if asynchronous else ast.FunctionDef
    return (isinstance(node, klass) and node.name.startswith('_') and
            not node.name.startswith('__') and not node.decorator_list and
            node.returns is None and node.type_comment is None and
            not getattr(node, 'type_params', ()) and
            not node.args.posonlyargs and not node.args.kwonlyargs and
            node.args.vararg is None and node.args.kwarg is None and
            not node.args.defaults and not node.args.kw_defaults and
            all(arg.annotation is None for arg in node.args.args))


def _print_call(stmt, name: str):
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return None
    call = stmt.value
    if (not isinstance(call.func, ast.Name) or call.func.id != 'print' or
        len(call.args) != 1 or call.keywords):
        return None
    called = call.args[0]
    if (not isinstance(called, ast.Call) or not isinstance(called.func, ast.Name)
            or called.func.id != name):
        return None
    return called


def _async_import(node):
    return (isinstance(node, ast.Import) and len(node.names) == 1 and
            node.names[0].name == 'asyncio' and node.names[0].asname is None)


def _async_print(stmt, name):
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    call = stmt.value
    if not (isinstance(call.func, ast.Name) and call.func.id == 'print'
            and len(call.args) == 1 and not call.keywords):
        return False
    runner = call.args[0]
    if not (isinstance(runner, ast.Call) and isinstance(runner.func, ast.Attribute)
            and isinstance(runner.func.value, ast.Name)
            and runner.func.value.id == 'asyncio'
            and runner.func.attr == 'run' and len(runner.args) == 1
            and not runner.keywords):
        return False
    awaited = runner.args[0]
    return (isinstance(awaited, ast.Call) and isinstance(awaited.func, ast.Name)
            and awaited.func.id == name and not awaited.args and not awaited.keywords)


def _closed(code, kind):
    info = _canonical(code)
    if info is None:
        return None
    tree, eol, ending = info
    nodes = tree.body
    async_kind = kind in ('async_def', 'await', 'async_structure')
    if len(nodes) != (3 if async_kind else 2):
        return None
    if async_kind:
        if not _async_import(nodes[0]):
            return None
        node, stmt = nodes[1:]
    else:
        node, stmt = nodes
    if not _private_fn(node, asynchronous=kind in ('await', 'async_structure')):
        return None
    if len(node.body) != 1:
        return None
    if async_kind and kind in ('await', 'async_structure'):
        if (node.args.args or not isinstance(node.body[0], ast.Return)
                or not _pure_literal_expression(node.body[0].value)
                or not _async_print(stmt, node.name)):
            return None
    elif kind == 'async_def':
        if (node.args.args or not isinstance(node.body[0], ast.Return)
                or not _pure_literal_expression(node.body[0].value)
                or _print_call(stmt, node.name) is None):
            return None
    else:
        if _print_call(stmt, node.name) is None:
            return None
    return node, stmt, eol, ending


def transform_default_parameter(code: str) -> str:
    info = _closed(code, 'default')
    if info is None:
        return code
    node, stmt, eol, ending = info
    if len(node.args.args) != 1 or not isinstance(node.body[0], ast.Return):
        return code
    param = node.args.args[0].arg
    expr = node.body[0].value
    if isinstance(expr, ast.Name) and expr.id == param:
        pass
    elif (isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.Add, ast.Mult))
          and isinstance(expr.left, ast.Name) and expr.left.id == param
          and isinstance(expr.right, ast.Constant)
          and type(expr.right.value) in (int, float)):
        pass
    else:
        return code
    called = _print_call(stmt, node.name)
    if len(called.args) != 1 or called.keywords or not _primitive(called.args[0]):
        return code
    if isinstance(expr, ast.BinOp) and type(called.args[0].value) is not type(expr.right.value):
        return code
    val = ast.unparse(called.args[0])
    return _finish([f'def {node.name}({param}={val}):', f'    return {ast.unparse(expr)}',
                    f'print({node.name}())'], eol, ending)


def _two_argument_return(code, kind):
    info = _closed(code, kind)
    if info is None:
        return None
    node, stmt, eol, ending = info
    if len(node.args.args) != 2 or not isinstance(node.body[0], ast.Return):
        return None
    a, b = (x.arg for x in node.args.args)
    ret = node.body[0].value
    if a == b or any(value in {'kwargs', 'args'} for value in (a, b)):
        return None
    # Name a +/-/* Name b, optionally followed by one numeric literal +1.
    main_op = ret
    if (isinstance(ret, ast.BinOp) and isinstance(ret.op, ast.Add)
            and isinstance(ret.right, ast.Constant) and type(ret.right.value) is int):
        main_op = ret.left
    if not (isinstance(main_op, ast.BinOp)
            and isinstance(main_op.op, (ast.Add, ast.Sub, ast.Mult))
            and isinstance(main_op.left, ast.Name) and main_op.left.id == a
            and isinstance(main_op.right, ast.Name) and main_op.right.id == b):
        return None
    call = _print_call(stmt, node.name)
    if kind == 'varargs':
        if len(call.args) != 2 or call.keywords or not all(_primitive(x) for x in call.args):
            return None
        args = [ast.unparse(x) for x in call.args]
        if type(call.args[0].value) is not type(call.args[1].value):
            return None
        if not isinstance(main_op.op, ast.Add) and type(call.args[0].value) not in (int, float):
            return None
        call_line = f'print({node.name}({", ".join(args)}))'
    else:
        if call.args or len(call.keywords) != 2:
            return None
        named = {kw.arg: kw.value for kw in call.keywords}
        if (set(named) != {a, b} or not all(_primitive(x) for x in named.values())
                or type(named[a].value) is not type(named[b].value)):
            return None
        if not isinstance(main_op.op, ast.Add) and type(named[a].value) not in (int, float):
            return None
        kwargs = ', '.join(f'{kw.arg}={ast.unparse(kw.value)}' for kw in call.keywords)
        call_line = f'print({node.name}({kwargs}))'
    if main_op is not ret:
        constant_types = ([type(x.value) for x in call.args] if kind == 'varargs'
                          else [type(named[a].value), type(named[b].value)])
        if any(t is not int for t in constant_types):
            return None
    return (node, a, b, ast.unparse(ret), call_line, eol, ending)


def transform_varargs_parameter(code: str) -> str:
    info = _two_argument_return(code, 'varargs')
    if info is None:
        return code
    node, a, b, ret_expr, called, eol, ending = info
    return _finish([f'def {node.name}(*args):', f'    {a}, {b} = args',
                    f'    return {ret_expr}', called], eol, ending)


def transform_kwargs_parameter(code: str) -> str:
    info = _two_argument_return(code, 'kwargs')
    if info is None:
        return code
    node, a, b, ret_expr, called, eol, ending = info
    return _finish([f'def {node.name}(**kwargs):',
                    f'    {a} = kwargs[{a!r}]', f'    {b} = kwargs[{b!r}]',
                    f'    return {ret_expr}', called], eol, ending)


def transform_async_function_definition(code: str) -> str:
    info = _closed(code, 'async_def')
    if info is None:
        return code
    node, _, eol, ending = info
    val = ast.unparse(node.body[0].value)
    return _finish(['import asyncio', f'async def {node.name}():',
                    f'    return {val}',
                    f'print(asyncio.run({node.name}()))'], eol, ending)


def transform_async_await(code: str) -> str:
    info = _closed(code, 'await')
    if info is None:
        return code
    node, _, eol, ending = info
    val = ast.unparse(node.body[0].value)
    return _finish(['import asyncio', f'async def {node.name}():',
                    f'    return await asyncio.sleep(0, result={val})',
                    f'print(asyncio.run({node.name}()))'], eol, ending)


def transform_async_processing_structure(code: str) -> str:
    info = _closed(code, 'async_structure')
    if info is None:
        return code
    node, _, eol, ending = info
    if node.name == '_runner':
        return code
    val = ast.unparse(node.body[0].value)
    return _finish(['import asyncio', f'async def {node.name}():',
                    f'    return {val}', 'async def _runner():',
                    f'    return await {node.name}()',
                    'print(asyncio.run(_runner()))'], eol, ending)


def transform_long_function_structure(code: str) -> str:
    info = _canonical(code)
    if info is None:
        return code
    tree, eol, ending = info
    if len(tree.body) != 2:
        return code
    node, invoked = tree.body
    if not _private_fn(node) or node.args.args or len(node.body) != 1:
        return code
    loop = node.body[0]
    if (not isinstance(loop, ast.For) or loop.orelse or not isinstance(loop.target, ast.Name)
            or not isinstance(loop.iter, (ast.List, ast.Tuple))
            or not 10 <= len(loop.iter.elts) <= 16
            or len(loop.body) != 1):
        return code
    if not all(_primitive(item) for item in loop.iter.elts):
        return code
    if not isinstance(loop.body[0], ast.Expr):
        return code
    call = loop.body[0].value
    if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
            or call.func.id != 'print' or call.keywords or len(call.args) != 1
            or not isinstance(call.args[0], ast.Name) or call.args[0].id != loop.target.id):
        return code
    if not isinstance(invoked, ast.Expr) or not isinstance(invoked.value, ast.Call):
        return code
    invocation = invoked.value
    if (not isinstance(invocation.func, ast.Name) or invocation.func.id != node.name
            or invocation.args or invocation.keywords):
        return code
    lines = [f'def {node.name}():']
    lines.extend('    print(' + ast.unparse(item) + ')' for item in loop.iter.elts)
    lines.append(f'{node.name}()')
    return _finish(lines, eol, ending)


TRANSFORMERS = {
    'create_safe_closed_default_parameter': transform_default_parameter,
    'create_safe_closed_varargs': transform_varargs_parameter,
    'create_safe_closed_kwargs': transform_kwargs_parameter,
    'create_safe_closed_async_definition': transform_async_function_definition,
    'create_safe_closed_await': transform_async_await,
    'create_safe_closed_async_structure': transform_async_processing_structure,
    'create_safe_closed_long_function': transform_long_function_structure,
}
