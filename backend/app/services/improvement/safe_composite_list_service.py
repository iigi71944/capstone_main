"""Batch36-4: narrowly scoped pure helper + list-comprehension compositions.

Do NOT broaden the existing general safe-list transform. First run it unchanged,
then consider a self-contained five-statement module with a literal integer
list, one pure scalar helper, a for/append pair, and print(output). This is a
conservative *syntactic* safeguard, not a general equivalence theorem.
"""
from __future__ import annotations

import ast
import io
import tokenize

from app.services.improvement.safe_list_comprehension_service import (
    transform_for_append_to_list_comprehension,
)

MAX_SOURCE_CHARS = 250_000


def _list_source(stmt: ast.stmt) -> tuple[str, ast.List] | None:
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.List)
            and 1 <= len(stmt.value.elts) <= 40
            and all(isinstance(x, ast.Constant) and type(x.value) is int
                    for x in stmt.value.elts)):
        return None
    return stmt.targets[0].id, stmt.value


def _helper(stmt: ast.stmt) -> tuple[str, str] | None:
    if isinstance(stmt, ast.FunctionDef):
        args = stmt.args
        if (stmt.decorator_list or stmt.returns or stmt.type_comment
                or getattr(stmt, 'type_params', None) or len(stmt.body) != 1
                or not isinstance(stmt.body[0], ast.Return)):
            return None
        body = stmt.body[0].value
        name = stmt.name
    elif (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
          and isinstance(stmt.targets[0], ast.Name)
          and isinstance(stmt.value, ast.Lambda)):
        args = stmt.value.args
        body = stmt.value.body
        name = stmt.targets[0].id
    else:
        return None
    if (name == 'print' or args.posonlyargs or args.vararg or args.kwarg
            or args.kwonlyargs or args.defaults or args.kw_defaults
            or len(args.args) != 1 or args.args[0].annotation is not None):
        return None
    param = args.args[0].arg
    if not (isinstance(body, ast.BinOp)
            and isinstance(body.op, (ast.Add, ast.Sub, ast.Mult))
            and isinstance(body.left, ast.Name) and body.left.id == param
            and isinstance(body.right, ast.Constant)
            and type(body.right.value) is int):
        return None
    return name, param


def _loop_pair(initial: ast.stmt, loop: ast.stmt) -> tuple[str, str, str, str] | None:
    if not (isinstance(initial, ast.Assign) and len(initial.targets) == 1
            and isinstance(initial.targets[0], ast.Name)
            and isinstance(initial.value, ast.List) and not initial.value.elts
            and isinstance(loop, ast.For) and len(loop.body) == 1
            and not loop.orelse and loop.type_comment is None
            and isinstance(loop.target, ast.Name)
            and isinstance(loop.iter, ast.Name)):
        return None
    statement = loop.body[0]
    if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)):
        return None
    call = statement.value
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == 'append'
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == initial.targets[0].id
            and not call.keywords and len(call.args) == 1):
        return None
    inner = call.args[0]
    if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            and not inner.keywords and len(inner.args) == 1
            and isinstance(inner.args[0], ast.Name)
            and inner.args[0].id == loop.target.id):
        return None
    return (initial.targets[0].id, loop.target.id, loop.iter.id, inner.func.id)


def _output_print(stmt: ast.stmt, output: str) -> bool:
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == 'print'
            and not stmt.value.keywords and len(stmt.value.args) == 1
            and isinstance(stmt.value.args[0], ast.Name)
            and stmt.value.args[0].id == output)


def _rewrite_closed_pure_helper_loop(code: str) -> str:
    if not isinstance(code, str) or not code or len(code) > MAX_SOURCE_CHARS:
        return code
    try:
        tree = ast.parse(code)
        if len(tree.body) != 5:
            return code
        source, helper_stmt, initial, loop, output = tree.body
        list_info = _list_source(source)
        helper_info = _helper(helper_stmt)
        pair = _loop_pair(initial, loop)
        if not list_info or not helper_info or not pair:
            return code
        list_name, _ = list_info
        helper_name, param_name = helper_info
        output_name, loop_name, iter_name, called_name = pair
        if (list_name != iter_name or helper_name != called_name
                or len({list_name, helper_name, output_name, loop_name}) != 4
                or param_name in {list_name, helper_name, output_name}
                or not all(name.isascii() for name in
                           (list_name, helper_name, param_name, output_name, loop_name))
                or not _output_print(output, output_name)):
            return code
        if tree.type_ignores:
            return code
        # The five-item closed shape precludes later loop-target reads,
        # unknown imports, mutations, nonlocal state, and call-site aliases.
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        if any(t.type == tokenize.COMMENT and initial.lineno <= t.start[0] <= loop.end_lineno
               for t in tokens):
            return code
        lines = code.splitlines(keepends=True)
        start_line = lines[initial.lineno - 1]
        last_line = lines[loop.end_lineno - 1]
        # No compound `;` statements, comments, or extra syntax on edited lines.
        if start_line[:initial.col_offset].strip() or last_line[loop.end_col_offset:].strip():
            return code
        if any(';' in line for line in lines[initial.lineno-1:loop.end_lineno]):
            return code
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line.encode('utf-8')))
        begin = offsets[initial.lineno-1] + initial.col_offset
        end = offsets[loop.end_lineno-1] + loop.end_col_offset
        new_stmt = ast.Assign(
            targets=[ast.Name(id=output_name, ctx=ast.Store())],
            value=ast.ListComp(
                elt=ast.Call(func=ast.Name(id=helper_name, ctx=ast.Load()),
                             args=[ast.Name(id=loop_name, ctx=ast.Load())], keywords=[]),
                generators=[ast.comprehension(
                    target=ast.Name(id=loop_name, ctx=ast.Store()),
                    iter=ast.Name(id=list_name, ctx=ast.Load()), ifs=[], is_async=0)],
            ),
        )
        rendered = ast.unparse(ast.fix_missing_locations(new_stmt)).encode('utf-8')
        original = code.encode('utf-8')
        if not (0 <= begin < end <= len(original)):
            return code
        modified = (original[:begin] + rendered + original[end:]).decode('utf-8')
        ast.parse(modified)
        return modified
    except (SyntaxError, UnicodeError, TypeError, ValueError, RecursionError,
            MemoryError, tokenize.TokenError, IndentationError):
        return code


def transform_safe_composite_list_comprehension(code: str) -> str:
    """Preserve original transformer; add a narrow, observable composition."""
    existing = transform_for_append_to_list_comprehension(code)
    if not isinstance(existing, str) or not existing.strip():
        return code
    return _rewrite_closed_pure_helper_loop(existing)


__all__ = ['transform_safe_composite_list_comprehension']
