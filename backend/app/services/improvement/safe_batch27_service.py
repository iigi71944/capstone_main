"""Batch 27: three guarded style transforms for Python scripts.

`open 사용`: in a tiny module `import io; h = io.open('name', 'r')`,
replace only the `io.open` function reference with `open`.
`파일 입출력 구조`: the analogous single top-level `with io.open(...):`
uses precisely the same runtime callable on CPython.
`절차형 코드 스타일`: inline a single private zero-argument _main/_run helper
whose entire body consists of literal print calls and whose only use is
one direct call; this is a *standalone script* transformation, not a
module-public-API-preserving refactor.

Open-based edits cannot be runtime-verified by the current restricted
execution sandbox; availability of an action does not prove an application.
"""
from __future__ import annotations

import ast
import builtins
import io

MAX_CHARS = 250_000
_ALLOWED_MODES = {'r', 'rt', 'rb'}


def _parse(code: str):
    if not isinstance(code, str) or not code or len(code) > MAX_CHARS:
        return None
    try:
        tree = ast.parse(code)
        source = code.encode('utf-8')
        offsets = [0]
        for line in code.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line.encode('utf-8')))
        return tree, source, offsets
    except (SyntaxError, TypeError, ValueError, UnicodeError, RecursionError, MemoryError):
        return None


def _span(node: ast.AST, offsets):
    return offsets[node.lineno - 1] + node.col_offset, offsets[node.end_lineno - 1] + node.end_col_offset


def _replace(code: str, data: bytes, edits):
    if not edits:
        return code
    last = len(data) + 1
    for start, end, new in sorted(edits, key=lambda x: x[0], reverse=True):
        if not (0 <= start < end <= last):
            return code
        data = data[:start] + new + data[end:]
        last = start
    try:
        updated = data.decode('utf-8')
        ast.parse(updated)
        return updated
    except (SyntaxError, ValueError, UnicodeError, RecursionError, MemoryError):
        return code


def _safe_io_call(tree: ast.Module, call: ast.AST) -> bool:
    """Require a two-statement, unshadowed CPython io.open call."""
    if io.open is not builtins.open or len(tree.body) != 2:
        return False
    header = tree.body[0]
    if not (isinstance(header, ast.Import) and len(header.names) == 1
            and header.names[0].name == 'io' and header.names[0].asname is None):
        return False
    if not (isinstance(call, ast.Call) and call.args and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == 'io' and call.func.attr == 'open'
            and isinstance(call.args[0], ast.Constant)):
        return False
    if type(call.args[0].value) is not str:
        return False
    if len(call.args) > 2 or any(kw.arg is None for kw in call.keywords):
        return False
    mode = 'r'
    if len(call.args) == 2:
        if not isinstance(call.args[1], ast.Constant) or type(call.args[1].value) is not str:
            return False
        mode = call.args[1].value
    for kw in call.keywords:
        if kw.arg not in {'mode', 'encoding'} or not isinstance(kw.value, ast.Constant):
            return False
        if type(kw.value.value) is not str:
            return False
        if kw.arg == 'mode':
            if len(call.args) == 2:
                return False
            mode = kw.value.value
    if mode not in _ALLOWED_MODES:
        return False
    if any(node.id == 'open' and isinstance(node.ctx, (ast.Store, ast.Del))
           for node in ast.walk(tree) if isinstance(node, ast.Name)):
        return False
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
           and node.func.id in {'exec', 'eval', 'globals', 'locals', 'vars', '__import__', 'setattr', 'delattr'}
           for node in ast.walk(tree)):
        return False
    return True


def transform_safe_module_io_open(code: str) -> str:
    """Rewrite `io.open` in a single top-level assignment, without file access."""
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    if len(tree.body) != 2 or not isinstance(tree.body[1], ast.Assign):
        return code
    assignment = tree.body[1]
    if (len(assignment.targets) != 1 or not isinstance(assignment.targets[0], ast.Name)
            or assignment.targets[0].id in {'io', 'open'}):
        return code
    if not _safe_io_call(tree, assignment.value):
        return code
    start, end = _span(assignment.value.func, offsets)
    if source[start:end] != b'io.open':
        return code
    return _replace(code, source, [(start, end, b'open')])


def transform_safe_file_io_with(code: str) -> str:
    """Rewrite `io.open` in a single top-level with-statement."""
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    if len(tree.body) != 2 or not isinstance(tree.body[1], ast.With):
        return code
    statement = tree.body[1]
    if len(statement.items) != 1 or not _safe_io_call(tree, statement.items[0].context_expr):
        return code
    start, end = _span(statement.items[0].context_expr.func, offsets)
    if source[start:end] != b'io.open':
        return code
    return _replace(code, source, [(start, end, b'open')])


def transform_literal_private_main_to_procedure(code: str) -> str:
    """Inline an isolated private literal-print function used only once.

    Standalone script semantics are preserved for print output. The private
    function's symbol is deliberately removed, so this transform is not
    suitable for libraries that expose or introspect module attributes.
    """
    parsed = _parse(code)
    if parsed is None:
        return code
    tree, source, offsets = parsed
    if len(tree.body) != 2:
        return code
    func, stmt = tree.body
    if not (isinstance(func, ast.FunctionDef) and func.name in {'_main', '_run', '_start'}
            and not func.decorator_list and not getattr(func, 'type_params', [])
            and not func.args.posonlyargs and not func.args.args
            and not func.args.kwonlyargs and func.args.vararg is None
            and func.args.kwarg is None and not func.args.defaults
            and not func.args.kw_defaults and func.returns is None
            and 1 <= len(func.body) <= 3
            and isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == func.name
            and not stmt.value.args and not stmt.value.keywords):
        return code
    if b'#' in source or b';' in source or b'\\' in source:
        return code
    lines = code.splitlines(keepends=True)
    if not lines or lines[0].rstrip('\r\n') != f'def {func.name}():':
        return code
    eol = '\r\n' if '\r\n' in code else '\n'
    out = []
    for item in func.body:
        if not (isinstance(item, ast.Expr) and isinstance(item.value, ast.Call)
                and isinstance(item.value.func, ast.Name)
                and item.value.func.id == 'print'
                and not item.value.keywords and 1 <= len(item.value.args) <= 3
                and all(isinstance(arg, ast.Constant) and type(arg.value) is str
                        for arg in item.value.args)):
            return code
        if item.lineno != item.end_lineno or item.lineno < 2:
            return code
        raw_line = lines[item.lineno - 1].rstrip('\r\n')
        if not raw_line.startswith('    print('):
            return code
        segment = ast.get_source_segment(code, item)
        if not segment or segment != raw_line[4:]:
            return code
        out.append(segment + eol)
    if stmt.lineno != stmt.end_lineno or lines[stmt.lineno - 1].rstrip('\r\n') != f'{func.name}()':
        return code
    # No comments, statements, imports, or other names may exist in the module.
    result = ''.join(out)
    if code.endswith('\n'):
        return result
    return result.rstrip('\r\n')
