"""Batch 12: source-preserving, deliberately restricted structural rewrites.

The matcher does not execute user code. It rejects shapes where equivalence
cannot be argued locally. A changed result still requires the existing
application-level execution checks; these are not general equivalence proofs.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import io
import re
import tokenize


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes


def _offsets(source: str) -> list[int]:
    result = [0]
    for line in source.splitlines(keepends=True):
        result.append(result[-1] + len(line.encode('utf-8')))
    return result


def _replace(source: str, edits: list[_Edit]) -> str:
    if not edits:
        return source
    data = source.encode('utf-8')
    selected: list[_Edit] = []
    for edit in sorted(edits, key=lambda e: (e.start, e.end)):
        if not (0 <= edit.start < edit.end <= len(data)):
            return source
        if selected and edit.start < selected[-1].end:
            return source
        selected.append(edit)
    for edit in reversed(selected):
        data = data[:edit.start] + edit.replacement + data[edit.end:]
    transformed = data.decode('utf-8')
    ast.parse(transformed)
    return transformed


def _comment_lines(source: str) -> set[int]:
    return {tok.start[0] for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type == tokenize.COMMENT}


def transform_to_safe_guard_continue_style(source: str) -> str:
    """Trailing `if guard: pass; else: one_stmt` -> guarded `continue`.

    The if must be the final statement directly inside an ordinary for loop;
    the else must have just one single-line simple statement. Consequently
    continuing cannot skip any other user statement in the iteration.
    Comments inside the replaced region, tabs, semicolons, multiline
    expressions and compound else bodies are all left unchanged.
    """
    try:
        tree = ast.parse(source)
        line_offsets = _offsets(source)
        lines = source.splitlines(keepends=True)
        comments = _comment_lines(source)
        edits: list[_Edit] = []
        for loop in ast.walk(tree):
            if not (isinstance(loop, ast.For) and loop.body):
                continue
            branch = loop.body[-1]
            if not (isinstance(branch, ast.If)
                    and len(branch.body) == 1
                    and isinstance(branch.body[0], ast.Pass)
                    and len(branch.orelse) == 1
                    and isinstance(branch.orelse[0], (ast.Expr, ast.Assign, ast.AugAssign))):
                continue
            tail = branch.orelse[0]
            if (branch.test.end_lineno != branch.test.lineno
                    or tail.end_lineno != tail.lineno
                    or branch.body[0].end_lineno != branch.body[0].lineno):
                continue
            if (not isinstance(branch.col_offset, int)
                    or branch.col_offset < 0 or branch.col_offset % 4 != 0):
                continue
            indent = ' ' * branch.col_offset
            if lines[branch.lineno - 1][:branch.col_offset] != indent:
                continue
            # Only standard, unambiguous line-oriented formatting is edited.
            if (lines[branch.body[0].lineno - 1][:branch.col_offset + 4]
                    != indent + '    '
                    or lines[tail.lineno - 1][:branch.col_offset + 4]
                    != indent + '    '):
                continue
            if any(branch.lineno <= n <= branch.end_lineno for n in comments):
                continue
            # Do not accidentally include semicolon-separated statements.
            if any(';' in lines[i - 1] for i in range(branch.lineno, branch.end_lineno + 1)):
                continue
            cond = ast.get_source_segment(source, branch.test)
            statement = ast.get_source_segment(source, tail)
            if cond is None or statement is None or '\n' in statement or '\r' in statement:
                continue
            newline = '\r\n' if '\r\n' in source else '\n'
            replacement = (f'if {cond}:{newline}{indent}    continue'
                           f'{newline}{indent}{statement}')
            begin = line_offsets[branch.lineno - 1] + branch.col_offset
            end = line_offsets[branch.end_lineno - 1] + branch.end_col_offset
            edits.append(_Edit(begin, end, replacement.encode('utf-8')))
        return _replace(source, edits)
    except (SyntaxError, tokenize.TokenError, ValueError, UnicodeError, IndexError):
        return source


def _static_primitive(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return type(node.value) in (int, float, bool, str, bytes, type(None))
    return (isinstance(node, ast.UnaryOp)
            and isinstance(node.op, (ast.USub, ast.UAdd))
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in (int, float))


def transform_to_safe_literal_identity_style(source: str) -> str:
    """Rewrite `x == None` / `None != x` only for *provable* local literals.

    `x` must be assigned a builtin primitive literal in the immediately
    preceding statement of the SAME block. This excludes custom __eq__
    implementations, call side effects and intervening rebindings. Only
    the comparison operator bytes change; comments and source layout stay.
    """
    try:
        tree = ast.parse(source)
        line_offsets = _offsets(source)
        data = source.encode('utf-8')
        edits: list[_Edit] = []
        for parent in ast.walk(tree):
            body = getattr(parent, 'body', None)
            if not (isinstance(body, list)
                    and all(isinstance(s, ast.stmt) for s in body)):
                continue
            for previous, current in zip(body, body[1:]):
                if not (isinstance(previous, ast.Assign)
                        and len(previous.targets) == 1
                        and isinstance(previous.targets[0], ast.Name)
                        and _static_primitive(previous.value)
                        and isinstance(current, ast.If)
                        and isinstance(current.test, ast.Compare)
                        and len(current.test.ops) == 1
                        and isinstance(current.test.ops[0], (ast.Eq, ast.NotEq))):
                    continue
                test = current.test
                first, second = test.left, test.comparators[0]
                local_name = previous.targets[0].id
                valid = ((isinstance(first, ast.Name) and first.id == local_name
                          and isinstance(second, ast.Constant) and second.value is None)
                         or (isinstance(second, ast.Name) and second.id == local_name
                             and isinstance(first, ast.Constant) and first.value is None))
                if not valid or first.end_lineno != second.lineno:
                    continue
                start = line_offsets[first.end_lineno - 1] + first.end_col_offset
                end = line_offsets[second.lineno - 1] + second.col_offset
                separator = data[start:end].decode('utf-8')
                m = re.fullmatch(r'([ \t]*)(==|!=)([ \t]*)', separator)
                if m is None:
                    continue
                operator = 'is' if isinstance(test.ops[0], ast.Eq) else 'is not'
                replacement = f'{m.group(1)}{operator}{m.group(3)}'.encode('utf-8')
                edits.append(_Edit(start, end, replacement))
        return _replace(source, edits)
    except (SyntaxError, tokenize.TokenError, ValueError, UnicodeError, IndexError):
        return source
