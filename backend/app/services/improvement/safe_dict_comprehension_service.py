"""Conservative bidirectional dict-comprehension/for-assignment transformation.

Standalone transformer: not wired to saved-style actions yet. This module avoids
changing earlier production transformers. Supported patterns are one generator,
synchronous loops, simple names/unpacking, optional nested filters, and direct
subscript assignment to a fresh empty dict. Comments inside edits, dynamic
namespace access, closures, calls (except a non-shadowed literal range), and
other potentially stateful or scope-sensitive syntax are skipped.

General Python iterator objects and instrumentation may expose observable scope
or allocation differences; this service is intentionally not a correctness
proof for arbitrary Python programs. The application's independent execution
validator remains necessary before applying results to user code.
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


_DYNAMIC_NAMES = {
    'locals', 'globals', 'vars', 'dir', 'eval', 'exec', 'compile',
    '__import__', 'sys', 'inspect', 'frame', 'getattr', 'setattr', 'delattr',
}
_UNSAFE_EXPR = (
    ast.Lambda, ast.NamedExpr, ast.Yield, ast.YieldFrom, ast.Await,
    ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.Attribute, ast.Subscript, ast.Starred,
)


def _literal_range_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == 'range'
        and not node.keywords
        and len(node.args) in (1, 2, 3)
        and all(
            isinstance(value, ast.Constant) and type(value.value) is int
            or isinstance(value, ast.UnaryOp)
               and isinstance(value.op, (ast.USub, ast.UAdd))
               and isinstance(value.operand, ast.Constant)
               and type(value.operand.value) is int
            for value in node.args
        )
    )


def _safe_expression(node: ast.AST, *, allow_range: bool = False) -> bool:
    for child in ast.walk(node):
        if isinstance(child, _UNSAFE_EXPR):
            return False
        if isinstance(child, ast.Name) and child.id in _DYNAMIC_NAMES:
            return False
        if isinstance(child, ast.Call):
            if not (allow_range and _literal_range_call(child)):
                return False
    return True


def _has_dynamic_names(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _DYNAMIC_NAMES:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name in ('*', 'sys', 'inspect'):
                    return True
    return False


def _range_shadowed(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == 'range' and isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        if isinstance(node, ast.arg) and node.arg == 'range':
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == 'range':
            return True
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.', 1)[0]) == 'range':
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and 'range' in node.names:
            return True
    return False


def _target_names(target: ast.expr) -> tuple[str, ...] | None:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, (ast.Tuple, ast.List)) and target.elts:
        names: list[str] = []
        for element in target.elts:
            found = _target_names(element)
            if found is None:
                return None
            names.extend(found)
        if len(names) == len(set(names)):
            return tuple(names)
    return None


def _comments(source: str) -> set[int]:
    return {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    }


def _statement_blocks(tree: ast.AST):
    """Do not rewrite any class-body suite (including nested if/try suites).

    Method function bodies are normal Python function scopes and are eligible.
    """
    def visit(node: ast.AST, class_body: bool = False):
        if isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                yield from visit(decorator, class_body)
            for statement in node.body:
                yield from visit(statement, True)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            class_body = False
        for _, field in ast.iter_fields(node):
            if isinstance(field, list) and field and all(isinstance(x, ast.stmt) for x in field):
                if not class_body:
                    yield field
            if isinstance(field, list):
                for child in field:
                    if isinstance(child, ast.AST):
                        yield from visit(child, class_body)
            elif isinstance(field, ast.AST):
                yield from visit(field, class_body)
    yield from visit(tree)


def _statement_span(source: str, first: ast.stmt, last: ast.stmt):
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
    return offsets[first.lineno - 1] + first.col_offset, offsets[last.end_lineno - 1] + last.end_col_offset, indent, newline


def _prepare_edit(source: str, first: ast.stmt, last: ast.stmt,
                  replacement: list[ast.stmt], commented: set[int]):
    if any(first.lineno <= row <= last.end_lineno for row in commented):
        return None
    span = _statement_span(source, first, last)
    if span is None:
        return None
    start, end, indent, newline = span
    rendered = ast.unparse(ast.fix_missing_locations(ast.Module(body=replacement, type_ignores=[])))
    return _Edit(start, end, (newline + indent).join(rendered.split('\n')).encode('utf-8'))


def _assignment_in_loop(loop: ast.For, output_name: str):
    if loop.orelse or loop.type_comment is not None or len(loop.body) != 1:
        return None
    statement = loop.body[0]
    conditions: list[ast.expr] = []
    while isinstance(statement, ast.If):
        if statement.orelse or len(statement.body) != 1:
            return None
        conditions.append(statement.test)
        statement = statement.body[0]
    if not (isinstance(statement, ast.Assign) and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Subscript)
            and isinstance(statement.targets[0].value, ast.Name)
            and statement.targets[0].value.id == output_name):
        return None
    return statement.targets[0].slice, statement.value, conditions


def _outside_name(tree: ast.AST, identifier: str, first: ast.stmt, last: ast.stmt) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == identifier:
            if node.lineno < first.lineno or node.lineno > last.end_lineno:
                return True
        elif isinstance(node, ast.arg) and node.arg == identifier:
            return True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == identifier:
            return True
        elif isinstance(node, ast.alias) and (node.asname or node.name.split('.', 1)[0]) == identifier:
            return True
        elif isinstance(node, (ast.Global, ast.Nonlocal)) and identifier in node.names:
            return True
    return False


def _collapse_pair(tree: ast.AST, first: ast.stmt, second: ast.stmt, allow_range: bool):
    if not (isinstance(first, ast.Assign) and len(first.targets) == 1
            and isinstance(first.targets[0], ast.Name)
            and isinstance(first.value, ast.Dict) and not first.value.keys
            and isinstance(second, ast.For)):
        return None
    result_name = first.targets[0].id
    target_names = _target_names(second.target)
    if not target_names or result_name in target_names:
        return None
    match = _assignment_in_loop(second, result_name)
    if match is None:
        return None
    key, value, conditions = match
    if not _safe_expression(second.iter, allow_range=allow_range):
        return None
    if not all(_safe_expression(expr) for expr in (key, value, *conditions)):
        return None
    if any(node.id == result_name for expr in (second.iter, key, value, *conditions)
           for node in ast.walk(expr) if isinstance(node, ast.Name)):
        return None
    if any(_outside_name(tree, name, first, second) for name in target_names):
        return None
    generator = ast.comprehension(
        target=copy.deepcopy(second.target), iter=copy.deepcopy(second.iter),
        ifs=[copy.deepcopy(cond) for cond in conditions], is_async=0,
    )
    expression = ast.DictComp(
        key=copy.deepcopy(key), value=copy.deepcopy(value), generators=[generator],
    )
    return [ast.Assign(targets=[copy.deepcopy(first.targets[0])], value=expression)]


def _used_names(tree: ast.AST):
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.arg):
            used.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            used.add(node.name)
        elif isinstance(node, ast.alias):
            used.add(node.asname or node.name.split('.', 1)[0])
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            used.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            used.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            used.add(node.name)
    return used


def _fresh(used: set[str], stem: str):
    sequence = 0
    while True:
        name = f'__capstone_{stem}_{sequence}'
        if name not in used:
            used.add(name)
            return name
        sequence += 1


class _ReplaceNames(ast.NodeTransformer):
    def __init__(self, rename: dict[str, str]):
        self.rename = rename

    def visit_Name(self, node: ast.Name):
        if node.id in self.rename:
            return ast.copy_location(ast.Name(self.rename[node.id], copy.deepcopy(node.ctx)), node)
        return node


def _expand_dict(stmt: ast.stmt, used: set[str], allow_range: bool):
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.DictComp)
            and len(stmt.value.generators) == 1):
        return None
    comp = stmt.value
    gen = comp.generators[0]
    names = _target_names(gen.target)
    if not names or gen.is_async:
        return None
    if not _safe_expression(gen.iter, allow_range=allow_range):
        return None
    if not all(_safe_expression(expr) for expr in (comp.key, comp.value, *gen.ifs)):
        return None
    if any(isinstance(node, ast.Name) and node.id == name for name in names
           for node in ast.walk(gen.iter)):
        # The source iterable may itself read a same-name outer variable.
        # Do not rewrite when scope resolution is potentially ambiguous.
        return None
    temp_result = _fresh(used, 'dict_result')
    rename = {name: _fresh(used, 'dict_item') for name in names}
    mapper = _ReplaceNames(rename)
    target = mapper.visit(copy.deepcopy(gen.target))
    key = mapper.visit(copy.deepcopy(comp.key))
    value = mapper.visit(copy.deepcopy(comp.value))
    conditions = [mapper.visit(copy.deepcopy(condition)) for condition in gen.ifs]
    put = ast.Assign(
        targets=[ast.Subscript(value=ast.Name(temp_result, ast.Load()), slice=key,
                               ctx=ast.Store())],
        value=value,
    )
    body: list[ast.stmt] = [put]
    for condition in reversed(conditions):
        body = [ast.If(test=condition, body=body, orelse=[])]
    loop = ast.For(
        target=target, iter=copy.deepcopy(gen.iter), body=body, orelse=[],
        type_comment=None,
    )
    initialization = [ast.Assign([ast.Name(temp_result, ast.Store())],
                                 ast.Dict(keys=[], values=[]))]
    initialization.extend(ast.Assign([ast.Name(new_name, ast.Store())],
                                      ast.Constant(None)) for new_name in rename.values())
    committed = ast.Assign(targets=[copy.deepcopy(stmt.targets[0])],
                           value=ast.Name(temp_result, ast.Load()))
    cleanup = ast.Delete(targets=[ast.Name(name, ast.Del())
                                  for name in [temp_result, *rename.values()]])
    guard = ast.Try(body=[loop, committed], handlers=[], orelse=[], finalbody=[cleanup])
    return [*initialization, guard]


def _rewrite(code: str, direction: str):
    try:
        tree = ast.parse(code)
        if _has_dynamic_names(tree):
            return code
        comment_lines = _comments(code)
        allow_range = not _range_shadowed(tree)
        used = _used_names(tree)
        edits: list[_Edit] = []
        for block in _statement_blocks(tree):
            if direction == 'collapse':
                for i in range(len(block) - 1):
                    first, second = block[i:i + 2]
                    lowered = _collapse_pair(tree, first, second, allow_range)
                    if lowered is None:
                        continue
                    edit = _prepare_edit(code, first, second, lowered, comment_lines)
                    if edit is not None and not any(edit.start < item.end and item.start < edit.end for item in edits):
                        edits.append(edit)
            elif direction == 'expand':
                for stmt in block:
                    if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.DictComp)):
                        continue
                    lowered = _expand_dict(stmt, used, allow_range)
                    if lowered is None:
                        continue
                    edit = _prepare_edit(code, stmt, stmt, lowered, comment_lines)
                    if edit is not None and not any(edit.start < item.end and item.start < edit.end for item in edits):
                        edits.append(edit)
            else:
                raise ValueError('unknown direction')
        if not edits:
            return code
        output = code.encode('utf-8')
        for edit in sorted(edits, key=lambda item: item.start, reverse=True):
            output = output[:edit.start] + edit.replacement + output[edit.end:]
        transformed = output.decode('utf-8')
        ast.parse(transformed)
        return transformed
    except (SyntaxError, TypeError, UnicodeError, ValueError, tokenize.TokenError, RecursionError):
        return code


def transform_for_assignment_to_dict_comprehension(code: str) -> str:
    """Use a dict comprehension for supported direct key/value accumulation."""
    return _rewrite(code, 'collapse')


def transform_dict_comprehension_to_for_assignment(code: str) -> str:
    """Expand supported dict comprehensions without leaking target names."""
    return _rewrite(code, 'expand')
