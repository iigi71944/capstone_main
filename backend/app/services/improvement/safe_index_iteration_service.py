"""Conservative, comment-aware conversion between indexed and direct Python loops.

The recognized iterable must be an ordinary local literal list/tuple/string/bytes
binding. This deliberately avoids changing generator evaluation, custom
__getitem__ behavior, or iteration over a list whose length can change.

Two public transformations:
  - for i in range(len(values)) -> for item in values / enumerate(values)
  - for item in values         -> for index in range(len(values))
                                  item = values[index]

Names fall back to __capstone_* when a preferred name already exists.

If semantic preservation cannot be established statically, return the source
unchanged rather than guessing. The surrounding source is never reformatted.
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


# Both injected builtins and explicit loop-related builtins must be genuine.
_BUILTINS = {"range", "len", "enumerate", "print"}
_INTROSPECTION = {"locals", "globals", "vars", "dir", "eval", "exec", "compile", "__import__"}
_UNSAFE_STATEMENTS = (
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
    ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
    ast.Match, ast.Global, ast.Nonlocal,
)
_UNSAFE_EXPRESSIONS = (
    ast.Lambda, ast.Yield, ast.YieldFrom, ast.Await,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
)


def _is_shadowed(tree: ast.AST) -> bool:
    """Module-wide conservative guard against shadowed injected builtins."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in _INTROSPECTION:
                return True
            if node.id in _BUILTINS and isinstance(node.ctx, (ast.Store, ast.Del)):
                return True
        elif isinstance(node, ast.arg) and node.arg in _BUILTINS | _INTROSPECTION:
            return True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in _BUILTINS | _INTROSPECTION:
                return True
        elif isinstance(node, ast.alias):
            binding = node.asname or node.name.split(".", 1)[0]
            if binding in _BUILTINS | _INTROSPECTION or node.name == "*":
                return True
        elif isinstance(node, ast.ExceptHandler) and node.name in _BUILTINS | _INTROSPECTION:
            return True
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            if set(node.names) & (_BUILTINS | _INTROSPECTION):
                return True
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name in _BUILTINS | _INTROSPECTION:
            return True
    return False


def _fresh_name(used: set[str], stem: str, preferred: str | None = None) -> str:
    if preferred is not None and preferred not in used:
        used.add(preferred)
        return preferred
    number = 0
    while True:
        candidate = f"__capstone_{stem}_{number}"
        number += 1
        if candidate not in used:
            used.add(candidate)
            return candidate


def _all_names(tree: ast.AST) -> set[str]:
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names.update(node.arg for node in ast.walk(tree) if isinstance(node, ast.arg))
    names.update(node.name for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    names.update(node.asname or node.name.split(".", 1)[0]
                 for node in ast.walk(tree) if isinstance(node, ast.alias))
    names.update(node.name for node in ast.walk(tree)
                 if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar))
                 and node.name is not None)
    names.update(name for node in ast.walk(tree)
                 if isinstance(node, (ast.Global, ast.Nonlocal))
                 for name in node.names)
    return names


def _literal_iterable(value: ast.AST) -> bool:
    # The container length and the element selection mechanism are provable.
    if isinstance(value, ast.Constant):
        return isinstance(value.value, (str, bytes))
    if isinstance(value, (ast.List, ast.Tuple)):
        return all(_simple_literal(element) for element in value.elts)
    return False


def _simple_literal(value: ast.AST) -> bool:
    if isinstance(value, ast.Constant):
        return type(value.value) in (type(None), int, float, complex, bool, str, bytes)
    if isinstance(value, (ast.List, ast.Tuple)):
        return all(_simple_literal(v) for v in value.elts)
    if isinstance(value, (ast.Set,)):
        return all(_simple_literal(v) for v in value.elts)
    if isinstance(value, ast.Dict):
        return all(k is not None and _simple_literal(k) and _simple_literal(v)
                   for k, v in zip(value.keys, value.values))
    if isinstance(value, ast.UnaryOp) and isinstance(value.op, (ast.UAdd, ast.USub)):
        return isinstance(value.operand, ast.Constant) and type(value.operand.value) in (int, float, complex)
    return False


def _same_block_literal(body: list[ast.stmt], position: int, name: str) -> bool:
    """The most recent simple assignment to name is a literal iterable.

    Only accept independent simple assignments between it and the loop;
    aliases, imports, function calls and arbitrary side effects are rejected.
    """
    for statement in reversed(body[:position]):
        if (isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and statement.targets[0].id == name):
            return _literal_iterable(statement.value)
        if any(isinstance(child, ast.Name) and child.id == name
               for child in ast.walk(statement)):
            return False
        if isinstance(statement, ast.Assign):
            if (len(statement.targets) != 1
                    or not isinstance(statement.targets[0], ast.Name)
                    or not _simple_literal(statement.value)):
                return False
        elif not isinstance(statement, ast.Pass):
            return False
    return False


def _loop_body_safe(node: ast.For, iterable_name: str, extra_guarded: set[str] = frozenset()) -> bool:
    """No dynamic mutation, unsafe calls, implicit code evaluation or rebinding."""
    for stmt in node.body:
        for part in ast.walk(stmt):
            if isinstance(part, _UNSAFE_STATEMENTS + _UNSAFE_EXPRESSIONS):
                return False
            if isinstance(part, ast.Call):
                if not (isinstance(part.func, ast.Name)
                        and part.func.id == "print"):
                    return False
            if isinstance(part, ast.Name):
                if part.id in {iterable_name, *extra_guarded} and isinstance(part.ctx, (ast.Store, ast.Del)):
                    return False
                if part.id in _INTROSPECTION:
                    return False
            if isinstance(part, ast.ExceptHandler) and part.name in {iterable_name, *extra_guarded}:
                return False
            if (isinstance(part, ast.Subscript)
                    and isinstance(part.ctx, (ast.Store, ast.Del))
                    and isinstance(part.value, ast.Name)
                    and part.value.id == iterable_name):
                return False
            if (isinstance(part, ast.Attribute)
                    and isinstance(part.ctx, (ast.Store, ast.Del))
                    and isinstance(part.value, ast.Name)
                    and part.value.id == iterable_name):
                return False
    return True


def _subscript_matches(node: ast.AST, sequence: str, index: str) -> bool:
    return (isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and node.value.id == sequence
            and isinstance(node.slice, ast.Name)
            and node.slice.id == index)


class _ReplaceIndexSubscripts(ast.NodeTransformer):
    def __init__(self, sequence: str, index: str, item: str):
        self.sequence = sequence
        self.index = index
        self.item = item
        self.changed = 0

    def visit_Subscript(self, node: ast.Subscript):
        if _subscript_matches(node, self.sequence, self.index):
            self.changed += 1
            return ast.copy_location(ast.Name(id=self.item, ctx=ast.Load()), node)
        return self.generic_visit(node)


def _reads_index(node: ast.For, sequence: str, index: str) -> bool:
    """Index has any purpose beyond direct collection indexing."""
    matches: set[int] = set()
    for item in ast.walk(node):
        if _subscript_matches(item, sequence, index):
            matches.add(id(item.slice))
    return any(isinstance(item, ast.Name) and item.id == index
               and isinstance(item.ctx, ast.Load) and id(item) not in matches
               for item in ast.walk(node))


def _name_read_outside(tree: ast.AST, loop: ast.For, name: str) -> bool:
    """Detect external reads, including closures that might read loop state."""
    def visit(node: ast.AST) -> bool:
        if node is loop:
            return False
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
            return True
        return any(visit(child) for child in ast.iter_child_nodes(node))
    return visit(tree)


def _is_range_len(node: ast.AST) -> str | None:
    if not (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "range"
            and len(node.args) == 1 and not node.keywords):
        return None
    inner = node.args[0]
    if not (isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name) and inner.func.id == "len"
            and len(inner.args) == 1 and not inner.keywords
            and isinstance(inner.args[0], ast.Name)):
        return None
    return inner.args[0].id


def _valid_target(target: ast.AST) -> bool:
    if isinstance(target, ast.Name):
        return True
    if isinstance(target, (ast.Tuple, ast.List)):
        return bool(target.elts) and all(_valid_target(item) for item in target.elts)
    return False


def _target_names(target: ast.AST) -> set[str]:
    return {part.id for part in ast.walk(target) if isinstance(part, ast.Name)}


def _direct_node(node: ast.For, tree: ast.AST, used: set[str]) -> ast.For | None:
    if not isinstance(node.target, ast.Name) or node.type_comment is not None:
        return None
    index = node.target.id
    sequence = _is_range_len(node.iter)
    if sequence is None or index == sequence:
        return None
    if not _loop_body_safe(node, sequence, {index}):
        return None
    if not any(_subscript_matches(part, sequence, index) for part in ast.walk(node)):
        return None
    item = _fresh_name(used, "item", preferred="item")
    rewritten = copy.deepcopy(node)
    replacer = _ReplaceIndexSubscripts(sequence, index, item)
    rewritten.body = [replacer.visit(stmt) for stmt in rewritten.body]
    # Never rewrite the else clause's expression: it can run with zero
    # iterations, when a new item variable has never been bound.
    if not replacer.changed:
        return None
    # If i appears anywhere other than values[i], retain its lifetime and
    # value by using enumerate (including i's last value after the loop).
    keep_index = (
        _reads_index(node, sequence, index)
        or _name_read_outside(tree, node, index)
        or any(isinstance(part, ast.Name) and part.id == index
               and isinstance(part.ctx, ast.Load)
               for statement in node.orelse for part in ast.walk(statement))
    )
    if keep_index:
        rewritten.target = ast.Tuple(elts=[ast.Name(id=index, ctx=ast.Store()),
                                           ast.Name(id=item, ctx=ast.Store())], ctx=ast.Store())
        rewritten.iter = ast.Call(func=ast.Name(id="enumerate", ctx=ast.Load()),
                                  args=[ast.Name(id=sequence, ctx=ast.Load())], keywords=[])
    else:
        rewritten.target = ast.Name(id=item, ctx=ast.Store())
        rewritten.iter = ast.Name(id=sequence, ctx=ast.Load())
    return ast.fix_missing_locations(rewritten)


def _index_node(node: ast.For, used: set[str]) -> ast.For | None:
    if (node.type_comment is not None
            or not isinstance(node.iter, ast.Name)
            or not _valid_target(node.target)):
        return None
    sequence = node.iter.id
    if sequence in _target_names(node.target):
        return None
    if not _loop_body_safe(node, sequence):
        return None
    index = _fresh_name(used, "index", preferred="index")
    rewritten = copy.deepcopy(node)
    rewritten.target = ast.Name(id=index, ctx=ast.Store())
    rewritten.iter = ast.Call(
        func=ast.Name(id="range", ctx=ast.Load()),
        args=[ast.Call(func=ast.Name(id="len", ctx=ast.Load()),
                       args=[ast.Name(id=sequence, ctx=ast.Load())], keywords=[])],
        keywords=[],
    )
    binding = ast.Assign(
        targets=[copy.deepcopy(node.target)],
        value=ast.Subscript(value=ast.Name(id=sequence, ctx=ast.Load()),
                            slice=ast.Name(id=index, ctx=ast.Load()), ctx=ast.Load()),
    )
    rewritten.body.insert(0, binding)
    return ast.fix_missing_locations(rewritten)


def _candidate_blocks(tree: ast.AST):
    for owner in ast.walk(tree):
        for _, statements in ast.iter_fields(owner):
            if (isinstance(statements, list) and statements
                    and all(isinstance(x, ast.stmt) for x in statements)):
                for position, node in enumerate(statements):
                    if isinstance(node, ast.For):
                        yield statements, position, node


def _comments(code: str) -> set[int]:
    return {t.start[0] for t in tokenize.generate_tokens(io.StringIO(code).readline)
            if t.type == tokenize.COMMENT}


def _edit_span(code: str, node: ast.For, replacement: ast.For) -> _Edit | None:
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    lines = code.splitlines(keepends=True)
    if node.lineno > len(lines) or node.end_lineno > len(lines):
        return None
    startline = lines[node.lineno - 1].encode("utf-8")
    endline = lines[node.end_lineno - 1].encode("utf-8")
    prefix = startline[:node.col_offset]
    suffix = endline[node.end_col_offset:]
    if prefix.strip() or suffix.strip():
        return None
    try:
        indent = prefix.decode("utf-8")
    except UnicodeError:
        return None
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8")))
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    text = ("\n" + indent).join(ast.unparse(replacement).split("\n"))
    return _Edit(start, end, text.encode("utf-8"))


def _transform(code: str, goal: str) -> str:
    try:
        tree = ast.parse(code)
        if _is_shadowed(tree):
            return code
        comments = _comments(code)
        used = _all_names(tree)
        edits: list[_Edit] = []
        for block, pos, node in _candidate_blocks(tree):
            if any(node.lineno <= line <= node.end_lineno for line in comments):
                continue
            sequence = (_is_range_len(node.iter) if goal == "direct"
                        else node.iter.id if isinstance(node.iter, ast.Name) else None)
            if sequence is None or not _same_block_literal(block, pos, sequence):
                continue
            replacement = (_direct_node(node, tree, used) if goal == "direct"
                           else _index_node(node, used))
            if replacement is None:
                continue
            edit = _edit_span(code, node, replacement)
            if edit is None or any(edit.start < e.end and e.start < edit.end for e in edits):
                continue
            edits.append(edit)
        if not edits:
            return code
        output = code.encode("utf-8")
        for edit in sorted(edits, key=lambda e: e.start, reverse=True):
            output = output[:edit.start] + edit.replacement + output[edit.end:]
        transformed = output.decode("utf-8")
        ast.parse(transformed)
        return transformed
    except (SyntaxError, tokenize.TokenError, ValueError, UnicodeError, TypeError):
        return code


def transform_to_direct_iteration_style(code: str) -> str:
    """Turn safe indexed loops into direct/enumerated loops."""
    return _transform(code, goal="direct")


def transform_to_index_iteration_style(code: str) -> str:
    """Turn safe direct loops into indexed loops, retaining item bindings."""
    return _transform(code, goal="index")
