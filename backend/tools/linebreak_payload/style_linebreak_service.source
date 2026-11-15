"""Conservative, AST-preserving Python newline/blank-line preferences.

Only formatting of known statement boundaries and simple comma-separated
bracket groups is attempted. Comments, multiline string literals and complex
expressions are never reformatted. No user code is executed here.
"""
from __future__ import annotations

import ast
from collections import Counter
import io
import re
import tokenize
from typing import Any, Iterator

# A single saved style supplies a preference only when a category is observed.
CONTROL = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With,
           ast.AsyncWith, ast.Match)
try:
    CONTROL += (ast.TryStar,)
except AttributeError:
    pass
FUNCTION = (ast.FunctionDef, ast.AsyncFunctionDef)
OPEN_TO_CLOSE = {'[': ']', '{': '}', '(': ')'}
CLOSE_TO_OPEN = {v: k for k, v in OPEN_TO_CLOSE.items()}


def _tokenize(code: str) -> list[tokenize.TokenInfo]:
    return list(tokenize.generate_tokens(io.StringIO(code).readline))


def _mode(values: list[int]) -> int | None:
    if not values:
        return None
    counts = Counter(values)
    return min(counts, key=lambda n: (-counts[n], n))


def _start_lineno(node: ast.AST) -> int:
    n = getattr(node, 'lineno', 0)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        n = min([n] + [d.lineno for d in node.decorator_list])
    return n


def _is_import(node: ast.AST) -> bool:
    return isinstance(node, (ast.Import, ast.ImportFrom))


def _gap_category(parent: ast.AST, a: ast.AST, b: ast.AST) -> str | None:
    if isinstance(parent, ast.Module):
        if isinstance(a, FUNCTION) and isinstance(b, FUNCTION):
            return 'between_top_level_functions'
        if isinstance(a, ast.ClassDef) and isinstance(b, ast.ClassDef):
            return 'between_top_level_classes'
        if _is_import(a) and not _is_import(b):
            return 'after_imports'
    if isinstance(parent, ast.ClassDef) and isinstance(a, FUNCTION) and isinstance(b, FUNCTION):
        return 'between_class_methods'
    if isinstance(b, ast.Return):
        return 'before_return'
    if isinstance(b, CONTROL):
        return 'before_control_flow'
    if isinstance(a, CONTROL):
        return 'after_control_flow'
    return None


def _gaps(tree: ast.AST, lines: list[str]) -> Iterator[tuple[str, int, int, int]]:
    """Yield (category, first-between-line, past-last-between-line, #blanks)."""
    for parent in ast.walk(tree):
        for _, body in ast.iter_fields(parent):
            if not isinstance(body, list) or len(body) < 2:
                continue
            if not all(isinstance(n, ast.stmt) for n in body):
                continue
            for a, b in zip(body, body[1:]):
                category = _gap_category(parent, a, b)
                if not category:
                    continue
                last = getattr(a, 'end_lineno', 0)
                first = _start_lineno(b)
                if not last or first <= last or first > len(lines):
                    continue
                # Skip all cases with a comment or other non-whitespace trivia
                # between the statements, so we never detach a user comment.
                middle = lines[last:first - 1]
                if any(row.strip() for row in middle):
                    continue
                yield category, last, first - 1, len(middle)


def _bracket_groups(code: str) -> list[dict[str, Any]]:
    tokens = _tokenize(code)
    stack: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for index, tok in enumerate(tokens):
        if tok.type != tokenize.OP:
            # Last significant token may be NAME/NUMBER/STRING, not only OP.
            # This matters for distinguishing `[1, 2]` from `[1, 2,]`.
            if stack and tok.type not in (tokenize.NL, tokenize.NEWLINE,
                                          tokenize.COMMENT, tokenize.INDENT,
                                          tokenize.DEDENT, tokenize.ENDMARKER):
                stack[-1]['last_token'] = tok
            continue
        if tok.string in OPEN_TO_CLOSE:
            group = {'open': tok, 'open_index': index, 'nested': False,
                     'commas': [], 'last_token': None}
            if stack:
                stack[-1]['nested'] = True
            stack.append(group)
        elif tok.string in CLOSE_TO_OPEN:
            if not stack or stack[-1]['open'].string != CLOSE_TO_OPEN[tok.string]:
                continue
            group = stack.pop()
            group['close'] = tok
            group['close_index'] = index
            group['trailing_comma'] = (
                group['last_token'] is not None and group['last_token'].string == ','
            )
            groups.append(group)
        elif tok.string == ',' and stack:
            stack[-1]['commas'].append(tok)
        if stack and tok.string not in OPEN_TO_CLOSE:
            stack[-1]['last_token'] = tok
    return groups


def _eligible_bracket_group(group: dict[str, Any], code: str) -> bool:
    opener = group['open']
    kind = opener.string
    if kind not in OPEN_TO_CLOSE or group['nested']:
        return False
    if len(group['commas']) < 1:
        return False
    # []/{} must look like literal collections, not indexing or slicing.
    line = code.splitlines()[opener.start[0] - 1]
    prefix = line[:opener.start[1]].rstrip()
    if kind in '[{' and prefix and (prefix[-1].isalnum() or prefix[-1] in '_)]}'):
        # `return [..]` / `yield {...}` are valid literal contexts.
        if not prefix.endswith(('return', 'yield')):
            return False
    # Do not edit def/class argument lists, even if the source sample used them.
    if kind == '(' and re.search(r'\b(?:def|class)\s+\w+\s*$', prefix):
        return False
    return True


def _length_metrics(code: str) -> int:
    lengths = [len(row.expandtabs(8)) for row in code.splitlines()
               if row.strip() and not row.lstrip().startswith('#')]
    return max(lengths, default=0)


def extract_linebreak_preferences(code: str) -> dict[str, Any]:
    """Returns JSON-compatible observed context and bracket-layout preferences."""
    lines = code.splitlines(keepends=True)
    tree = ast.parse(code)
    contexts: dict[str, list[int]] = {}
    for category, _, _, size in _gaps(tree, lines):
        contexts.setdefault(category, []).append(size)
    blank = {}
    for key, sizes in sorted(contexts.items()):
        histogram = Counter(sizes)
        blank[key] = {
            'preferred': _mode(sizes),
            'observations': len(sizes),
            'histogram': {str(n): count for n, count in sorted(histogram.items())},
        }

    brackets: dict[str, dict[str, int]] = {}
    for group in _bracket_groups(code):
        if not _eligible_bracket_group(group, code):
            continue
        kind = group['open'].string
        values = brackets.setdefault(kind, {'multiline': 0, 'single_line': 0,
                                            'multiline_trailing_comma': 0})
        if group['open'].start[0] != group['close'].start[0]:
            values['multiline'] += 1
            if group['trailing_comma']:
                values['multiline_trailing_comma'] += 1
        else:
            values['single_line'] += 1
    return {
        'blank_lines_by_context': blank,
        'bracket_groups_by_kind': brackets,
        'observed_max_code_columns': _length_metrics(code),
    }


def _newline(code: str) -> str:
    if '\r\n' in code:
        return '\r\n'
    if '\r' in code and '\n' not in code:
        return '\r'
    return '\n'


def apply_context_blank_lines(code: str, layout: dict[str, Any]) -> str:
    contexts = layout.get('blank_lines_by_context')
    if not isinstance(contexts, dict) or not contexts:
        return code
    lines = code.splitlines(keepends=True)
    tree = ast.parse(code)
    edits: list[tuple[int, int, int]] = []
    for category, start, end, existing in _gaps(tree, lines):
        data = contexts.get(category)
        if not isinstance(data, dict) or type(data.get('preferred')) is not int:
            continue
        if type(data.get('observations')) is not int or data['observations'] < 1:
            continue
        desired = data['preferred']
        if not (0 <= desired <= 3) or desired == existing:
            continue
        edits.append((start, end, desired))
    if not edits:
        return code
    eol = _newline(code)
    for start, end, desired in sorted(edits, reverse=True):
        lines[start:end] = [eol] * desired
    return ''.join(lines)


def _item_strings_on_single_line(code: str, group: dict[str, Any]) -> list[str] | None:
    op, cl = group['open'], group['close']
    if op.start[0] != cl.start[0]:
        return None
    line = code.splitlines()[op.start[0] - 1]
    boundaries = [op.start[1] + 1] + [t.start[1] + 1 for t in group['commas']]
    ends = [t.start[1] for t in group['commas']] + [cl.start[1]]
    if len(boundaries) != len(ends):
        return None
    parts = [line[a:b].strip() for a, b in zip(boundaries, ends)]
    if group['trailing_comma']:
        parts = parts[:-1]
    if len(parts) < 2 or not all(parts):
        return None
    if any('\\' in p for p in parts):
        return None
    return parts


def _is_bracket_tail(code: str, group: dict[str, Any]) -> bool:
    close = group['close']
    line = code.splitlines()[close.start[0] - 1]
    rest = line[close.end[1]:].strip()
    return not rest or rest.startswith('#')


def _wrap_one(code: str, kind: str, trailing: bool, unit: str, min_width: int = 0) -> str:
    lines = code.splitlines(keepends=True)
    for group in _bracket_groups(code):
        if group['open'].string != kind or not _eligible_bracket_group(group, code):
            continue
        if not _is_bracket_tail(code, group):
            continue
        parts = _item_strings_on_single_line(code, group)
        if parts is None or len(parts) > 40:
            continue
        row, col = group['open'].start
        end = group['close'].start[1]
        line = lines[row - 1]
        if min_width and len(line.expandtabs(8).rstrip('\r\n')) <= min_width:
            continue
        eol = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else '\r' if line.endswith('\r') else ''
        content = line[:-len(eol)] if eol else line
        indent = re.match(r'[ \t]*', content).group()
        prefix = content[:col + 1]
        suffix = content[end:]
        separator = _newline(code)
        indent_item = indent + unit
        items = [indent_item + p + (',' if idx < len(parts)-1 or trailing else '')
                 for idx, p in enumerate(parts)]
        lines[row - 1] = (prefix + separator + separator.join(items) + separator +
                          indent + suffix + eol)
        return ''.join(lines)
    return code


def _unwrap_one(code: str, kind: str, max_width: int) -> str:
    lines = code.splitlines(keepends=True)
    for group in _bracket_groups(code):
        if group['open'].string != kind or not _eligible_bracket_group(group, code):
            continue
        op, cl = group['open'], group['close']
        if op.start[0] >= cl.start[0] or not _is_bracket_tail(code, group):
            continue
        first = lines[op.start[0] - 1].rstrip('\r\n')
        last = lines[cl.start[0] - 1].rstrip('\r\n')
        if first[op.end[1]:].strip() or last[:cl.start[1]].strip():
            continue
        middle = lines[op.start[0]:cl.start[0] - 1]
        if len(middle) < 2 or len(middle) > 40:
            continue
        parts = []
        for row in middle:
            part = row.strip()
            if not part or not part.endswith(',') or '#' in part or '\\' in part:
                break
            parts.append(part[:-1].strip())
        else:
            if not all(parts):
                continue
            content = first + ', '.join(parts) + last[cl.start[1]:]
            if len(content.expandtabs(8)) > max_width:
                continue
            eol = '\r\n' if lines[cl.start[0] - 1].endswith('\r\n') else '\n' if lines[cl.start[0] - 1].endswith('\n') else ''
            lines[op.start[0] - 1:cl.start[0]] = [content + eol]
            return ''.join(lines)
    return code


def apply_bracket_linebreaks(code: str, layout: dict[str, Any], unit: str) -> str:
    groups = layout.get('bracket_groups_by_kind')
    if not isinstance(groups, dict):
        return code
    candidate = code
    limit = layout.get('observed_max_code_columns')
    limit = min(120, max(88, limit)) if type(limit) is int and limit >= 0 else 88
    for kind in ('[', '{', '('):
        info = groups.get(kind)
        if not isinstance(info, dict):
            continue
        multi, single = info.get('multiline'), info.get('single_line')
        if type(multi) is not int or type(single) is not int or multi < 0 or single < 0:
            continue
        if multi >= 1:
            # A mixed style usually keeps short expressions in one line and
            # wraps only long ones; preserve that distinction.
            minimum = 0 if multi >= single else limit
            trailing_n = info.get('multiline_trailing_comma', 0)
            trailing = type(trailing_n) is int and trailing_n > multi // 2
            for _ in range(100):
                result = _wrap_one(candidate, kind, trailing, unit, minimum)
                if result == candidate:
                    break
                candidate = result
        elif single >= 1 and multi == 0:
            for _ in range(100):
                result = _unwrap_one(candidate, kind, limit)
                if result == candidate:
                    break
                candidate = result
    return candidate
