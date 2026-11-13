"""Reverse the iterator-based while template emitted by for_to_while_service.

This is not a general while -> for rule: it recognizes only the exact,
private-name template of our own for -> while lowering. Ordinary counted
while loops remain the responsibility of counted_while_to_for_service.py.
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


def _assignment_name(node: ast.stmt, prefix: str) -> str | None:
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
        return None
    target = node.targets[0]
    if isinstance(target, ast.Name) and target.id.startswith(prefix):
        return target.id
    return None


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _matches_group(body: list[ast.stmt], start: int):
    """Return (span end, original For) for a generated template only."""
    if start + 2 >= len(body):
        return None
    setup = body[start]
    iterator_name = _assignment_name(setup, "__capstone_iterator_")
    if iterator_name is None:
        return None
    if not (
        isinstance(setup.value, ast.Call)
        and _is_name(setup.value.func, "iter")
        and len(setup.value.args) == 1
        and not setup.value.keywords
    ):
        return None
    pulled_setup = body[start + 1]
    pulled_name = _assignment_name(pulled_setup, "__capstone_pulled_")
    if pulled_name is None or not (
        isinstance(pulled_setup.value, ast.Constant)
        and pulled_setup.value.value is None
    ):
        return None
    index = start + 2
    finished_name = None
    if index < len(body):
        finished_setup = body[index]
        candidate = _assignment_name(finished_setup, "__capstone_finished_")
        if candidate and isinstance(finished_setup.value, ast.Constant):
            if finished_setup.value.value is False:
                finished_name = candidate
                index += 1
    if index >= len(body):
        return None
    guard = body[index]
    if not (isinstance(guard, ast.Try) and not guard.handlers and not guard.orelse):
        return None
    expected = 2 if finished_name else 1
    if len(guard.body) != expected or len(guard.finalbody) != 1:
        return None
    cleanup = guard.finalbody[0]
    if not isinstance(cleanup, ast.Delete):
        return None
    deleted = [item.id for item in cleanup.targets if isinstance(item, ast.Name)]
    want = [iterator_name, pulled_name]
    if finished_name:
        want.append(finished_name)
    if deleted != want:
        return None
    loop = guard.body[0]
    if not (isinstance(loop, ast.While)
            and isinstance(loop.test, ast.Constant)
            and loop.test.value is True
            and not loop.orelse
            and len(loop.body) >= 2):
        return None
    pull = loop.body[0]
    bind = loop.body[1]
    if not (
        isinstance(pull, ast.Try)
        and len(pull.body) == 1
        and len(pull.handlers) == 1
        and not pull.orelse
        and not pull.finalbody
        and isinstance(bind, ast.Assign)
        and len(bind.targets) == 1
        and _is_name(bind.value, pulled_name)
    ):
        return None
    pull_assign = pull.body[0]
    if not (
        isinstance(pull_assign, ast.Assign)
        and len(pull_assign.targets) == 1
        and _is_name(pull_assign.targets[0], pulled_name)
        and isinstance(pull_assign.value, ast.Call)
        and _is_name(pull_assign.value.func, "next")
        and len(pull_assign.value.args) == 1
        and _is_name(pull_assign.value.args[0], iterator_name)
        and not pull_assign.value.keywords
    ):
        return None
    handler = pull.handlers[0]
    if not (_is_name(handler.type, "StopIteration") and handler.name is None):
        return None
    if finished_name:
        if len(handler.body) != 2:
            return None
        mark, stop = handler.body
        if not (
            _assignment_name(mark, "__capstone_finished_") == finished_name
            and isinstance(mark.value, ast.Constant)
            and mark.value.value is True
            and isinstance(stop, ast.Break)
        ):
            return None
        else_wrapper = guard.body[1]
        if not (
            isinstance(else_wrapper, ast.If)
            and _is_name(else_wrapper.test, finished_name)
            and not else_wrapper.orelse
        ):
            return None
        orelse = copy.deepcopy(else_wrapper.body)
    else:
        if len(handler.body) != 1 or not isinstance(handler.body[0], ast.Break):
            return None
        orelse = []
    if not loop.body[2:]:
        return None
    original = ast.For(
        target=copy.deepcopy(bind.targets[0]),
        iter=copy.deepcopy(setup.value.args[0]),
        body=copy.deepcopy(loop.body[2:]),
        orelse=orelse,
        type_comment=None,
    )
    ast.fix_missing_locations(original)
    return index, original


def _statement_blocks(tree: ast.AST):
    for scope in ast.walk(tree):
        for _, value in ast.iter_fields(scope):
            if isinstance(value, list) and value and all(isinstance(x, ast.stmt) for x in value):
                yield value


def _span(source: str, first: ast.stmt, last: ast.stmt):
    if last.end_lineno is None or last.end_col_offset is None:
        return None
    lines = source.splitlines(keepends=True)
    if first.lineno > len(lines) or last.end_lineno > len(lines):
        return None
    prefix = lines[first.lineno - 1].encode("utf-8")[:first.col_offset]
    suffix = lines[last.end_lineno - 1].encode("utf-8")[last.end_col_offset:]
    if prefix.strip() or suffix.strip():
        return None
    try:
        indent = prefix.decode("utf-8")
    except UnicodeError:
        return None
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8")))
    return (
        offsets[first.lineno - 1] + first.col_offset,
        offsets[last.end_lineno - 1] + last.end_col_offset,
        indent,
    )


def restore_iterator_for_loops(code: str) -> str:
    """Restore for statements lowered by this project, preserving other text."""
    try:
        tree = ast.parse(code)
        commented = {
            token.start[0]
            for token in tokenize.generate_tokens(io.StringIO(code).readline)
            if token.type == tokenize.COMMENT
        }
        edits = []
        for block in _statement_blocks(tree):
            position = 0
            while position < len(block):
                result = _matches_group(block, position)
                if result is None:
                    position += 1
                    continue
                last_index, original = result
                first, last = block[position], block[last_index]
                if any(first.lineno <= line <= last.end_lineno for line in commented):
                    position = last_index + 1
                    continue
                span = _span(code, first, last)
                if span is not None:
                    start, end, indent = span
                    replacement = ("\n" + indent).join(ast.unparse(original).split("\n"))
                    if not any(start < item.end and item.start < end for item in edits):
                        edits.append(_Edit(start, end, replacement.encode("utf-8")))
                position = last_index + 1
        if not edits:
            return code
        output = code.encode("utf-8")
        for item in sorted(edits, key=lambda x: x.start, reverse=True):
            output = output[:item.start] + item.replacement + output[item.end:]
        updated = output.decode("utf-8")
        ast.parse(updated)
        return updated
    except (SyntaxError, tokenize.TokenError, UnicodeError, ValueError, TypeError):
        return code
