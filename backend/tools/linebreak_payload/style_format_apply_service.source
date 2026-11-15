"""Apply a saved Python formatting profile conservatively, without executing code.

This service is independent of syntax/concept tags.  Only version-1 profiles
are accepted.  Every edit must preserve the parsed AST (excluding locations).
Unsupported formatting preferences are not guessed or fabricated.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from typing import Any


class FormattingProfileError(ValueError):
    """Saved format profile is malformed or unsupported."""


def _ast_signature(code: str) -> str:
    return ast.dump(ast.parse(code), include_attributes=False)


def _tokens(code: str) -> list[tokenize.TokenInfo]:
    return list(tokenize.generate_tokens(io.StringIO(code).readline))


def _same_ast(before: str, after: str) -> bool:
    try:
        return _ast_signature(before) == _ast_signature(after)
    except (SyntaxError, ValueError, TypeError):
        return False


def _indent_lines(code: str, kind: str, unit: int) -> str:
    """Change indentation of physical *statement* lines, never string contents.

    INDENT/DEDENT tokens, not guessed numbers of spaces, establish each block's
    actual nesting depth.  Continuation lines and multi-line strings are left
    untouched.  Comment-only lines follow matching statement indentation.
    """
    tokens = _tokens(code)
    lines = code.splitlines(keepends=True)
    indent_depth = 0
    bracket_depth = 0
    statement_first_line: int | None = None
    multiline_string_lines: set[int] = set()
    code_line_depths: dict[int, int] = {}

    for token in tokens:
        typ, value = token.type, token.string
        if typ == tokenize.INDENT:
            indent_depth += 1
            continue
        if typ == tokenize.DEDENT:
            indent_depth -= 1
            if indent_depth < 0:
                return code
            continue
        if typ == tokenize.NEWLINE:
            statement_first_line = None
            continue
        if typ == tokenize.STRING and token.end[0] > token.start[0]:
            multiline_string_lines.update(range(token.start[0] + 1, token.end[0] + 1))
        if typ in (tokenize.NL, tokenize.COMMENT, tokenize.ENDMARKER, tokenize.ENCODING):
            continue

        if statement_first_line is None:
            statement_first_line = token.start[0]
        if (
            statement_first_line == token.start[0]
            and bracket_depth == 0
            and token.start[0] not in multiline_string_lines
        ):
            code_line_depths.setdefault(token.start[0], indent_depth)
        if typ == tokenize.OP:
            if value in '([{':
                bracket_depth += 1
            elif value in ')]}' and bracket_depth:
                bracket_depth -= 1

    if not code_line_depths:
        return code

    pref_map: dict[str, str] = {}
    new_lines = lines[:]
    for line_no, depth in sorted(code_line_depths.items()):
        if line_no > len(lines):
            continue
        line = lines[line_no - 1]
        found = re.match(r'[ \t]*', line)
        old = found.group() if found else ''
        target = ('\t' * depth) if kind == 'tabs' else (' ' * (unit * depth))
        if old in pref_map and pref_map[old] != target:
            # A single lexical prefix mapped to incompatible block depths.
            return code
        pref_map[old] = target
        new_lines[line_no - 1] = target + line[len(old):]

    # Comment-only lines may be inside a block before its first statement.
    # Replace them only where the original prefix maps unambiguously.
    for index, line in enumerate(lines):
        if index + 1 in code_line_depths or index + 1 in multiline_string_lines:
            continue
        if not line.lstrip(' \t').startswith('#'):
            continue
        old = re.match(r'[ \t]*', line).group()
        if old in pref_map:
            new_lines[index] = pref_map[old] + line[len(old):]
    return ''.join(new_lines)


def _semicolon_lines(code: str) -> str:
    """Split simple single-physical-line statements on real semicolon tokens.

    Compound inline suites (e.g. `if cond: x=1; y=2`) are not rewritten.
    The AST equivalence gate additionally rejects anything unsafe.
    """
    tokens = _tokens(code)
    lines = code.splitlines(keepends=True)
    semis_by_line: dict[int, list[int]] = {}
    blocked_lines: set[int] = set()
    bracket_depth = 0
    statement_first_line: int | None = None
    multiline_string_lines: set[int] = set()
    colon_before: set[int] = set()

    for token in tokens:
        typ, value = token.type, token.string
        row = token.start[0]
        if typ == tokenize.STRING and token.end[0] > row:
            multiline_string_lines.update(range(row, token.end[0] + 1))
        if typ == tokenize.NEWLINE:
            statement_first_line = None
            continue
        if typ in (tokenize.INDENT, tokenize.DEDENT, tokenize.NL, tokenize.COMMENT, tokenize.ENDMARKER):
            continue
        if statement_first_line is None:
            statement_first_line = row
        if row != statement_first_line:
            blocked_lines.add(row)
            blocked_lines.add(statement_first_line)
        if typ != tokenize.OP:
            continue
        if value in '([{':
            bracket_depth += 1
        elif value in ')]}' and bracket_depth:
            bracket_depth -= 1
        elif bracket_depth == 0 and value == ':':
            colon_before.add(row)
        elif bracket_depth == 0 and value == ';':
            semis_by_line.setdefault(row, []).append(token.start[1])

    result = lines[:]
    for row, cols in semis_by_line.items():
        if row > len(lines) or row in blocked_lines or row in multiline_string_lines or row in colon_before:
            continue
        original = lines[row - 1]
        if original.endswith('\r\n'):
            content, ending = original[:-2], '\r\n'
        elif original.endswith(('\n', '\r')):
            content, ending = original[:-1], original[-1]
        else:
            content, ending = original, ''
        if not cols or any(c >= len(content) for c in cols):
            continue
        starts = [0] + [c + 1 for c in cols]
        ends = cols + [len(content)]
        chunks = [content[a:b] for a, b in zip(starts, ends)]
        if any(not s.strip() for s in chunks):
            continue
        # Inline comments before a separator would make the later statement
        # a comment after splitting.  Treat as unsupported, not as a fix.
        if any('#' in s for s in chunks[:-1]):
            continue
        indent = re.match(r'[ \t]*', original).group()
        result[row - 1] = ending.join([chunks[0].rstrip()] + [indent + s.lstrip(' \t') for s in chunks[1:]]) + ending
    return ''.join(result)


def _combine_simple_assignments(code: str) -> str:
    """Conservatively join adjacent assignments in one block onto one line.

    Never merge calls, control-flow headers, comments, multiline statements or
    unrelated scopes. This covers common `a = 1; b = 2` / `x += 1; y += 1`
    preferences, not arbitrary line-joining requests.
    """
    tree = ast.parse(code)
    tokens = _tokens(code)
    comment_rows = {tok.start[0] for tok in tokens if tok.type == tokenize.COMMENT}
    lines = code.splitlines(keepends=True)
    pairs: dict[int, int] = {}
    safe_types = (ast.Assign, ast.AnnAssign, ast.AugAssign)

    for scope in ast.walk(tree):
        for _, block in ast.iter_fields(scope):
            if not isinstance(block, list) or not block or not all(isinstance(node, ast.stmt) for node in block):
                continue
            idx = 0
            while idx + 1 < len(block):
                a, b = block[idx:idx + 2]
                if not isinstance(a, safe_types) or not isinstance(b, safe_types):
                    idx += 1
                    continue
                a_start = getattr(a, 'lineno', 0)
                b_start = getattr(b, 'lineno', 0)
                if (
                    a_start < 1 or b_start != a_start + 1
                    or a.end_lineno != a_start or b.end_lineno != b_start
                    or a_start in comment_rows or b_start in comment_rows
                    or b_start > len(lines)
                    or a_start in pairs or b_start in pairs
                ):
                    idx += 1
                    continue
                left = lines[a_start - 1]
                right = lines[b_start - 1]
                left_indent = re.match(r'[ \t]*', left).group()
                right_indent = re.match(r'[ \t]*', right).group()
                if left_indent != right_indent:
                    idx += 1
                    continue
                left_body = left.rstrip('\r\n').rstrip(' \t')
                right_body = right[len(right_indent):].rstrip('\r\n')
                if (
                    not left_body or not right_body.strip()
                    or left_body.rstrip().endswith(('\\', ';'))
                    or len(left_body) + len(right_body.strip()) + 2 > 120
                ):
                    idx += 1
                    continue
                pairs[a_start] = b_start
                idx += 2
    if not pairs:
        return code
    out: list[str] = []
    row = 1
    while row <= len(lines):
        if row in pairs:
            second = pairs[row]
            left = lines[row - 1]
            right = lines[second - 1]
            indent = re.match(r'[ \t]*', right).group()
            ending = ('\r\n' if right.endswith('\r\n') else
                      '\n' if right.endswith('\n') else
                      '\r' if right.endswith('\r') else '')
            out.append(left.rstrip('\r\n').rstrip(' \t') + '; ' +
                       right[len(indent):].rstrip('\r\n').strip(' \t') + ending)
            row += 2
            continue
        out.append(lines[row - 1])
        row += 1
    return ''.join(out)


def _remove_excess_blank_lines(code: str, preferred_limit: int) -> str:
    """Only shrink *excess* blank-line runs; never insert blank lines.

    Preserve at least one existing blank line for readability.  Multi-line
    string token spans and open-bracket regions are protected; an AST guard
    also rejects modifications that could change string constants.
    """
    lines = code.splitlines(keepends=True)
    tokens = _tokens(code)
    blocked: set[int] = set()
    bracket_depth = 0
    for token in tokens:
        if token.type == tokenize.STRING and token.end[0] > token.start[0]:
            blocked.update(range(token.start[0], token.end[0] + 1))
        if token.type == tokenize.OP:
            if token.string in '([{':
                bracket_depth += 1
            elif token.string in ')]}' and bracket_depth:
                bracket_depth -= 1
        if bracket_depth:
            blocked.add(token.start[0])
        if token.type == tokenize.NL and bracket_depth:
            blocked.add(token.start[0])
    limit = max(1, preferred_limit)
    result: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != '':
            result.append(lines[index]); index += 1; continue
        end = index
        while end < len(lines) and lines[end].strip() == '':
            end += 1
        run = lines[index:end]
        if index > 0 and end < len(lines) and len(run) > limit and not any(
            i in blocked for i in range(index, end + 2)
        ):
            result.extend(run[:limit])
        else:
            result.extend(run)
        index = end
    return ''.join(result)


def _profile_preference(profile: dict[str, Any]) -> tuple[str | None, int | None, bool | None, int | None]:
    if not isinstance(profile, dict) or type(profile.get('version')) is not int or profile.get('version') != 1:
        raise FormattingProfileError('지원하지 않는 서식 프로필입니다(version=1 필요).')
    indentation = profile.get('indentation')
    layout = profile.get('line_layout')
    if not isinstance(indentation, dict) or not isinstance(layout, dict):
        raise FormattingProfileError('서식 프로필의 들여쓰기/줄바꿈 데이터가 올바르지 않습니다.')
    kind = indentation.get('kind')
    unit = indentation.get('unit_columns')
    if kind is not None and kind not in ('spaces', 'tabs', 'mixed'):
        raise FormattingProfileError('지원하지 않는 들여쓰기 종류입니다.')
    if kind in ('spaces', 'tabs'):
        if type(unit) is not int or not (1 <= unit <= 16):
            raise FormattingProfileError('들여쓰기 단위는 1~16의 정수여야 합니다.')
        if kind == 'tabs' and unit != 8:
            raise FormattingProfileError('8열 탭 이외의 특수 탭 너비는 적용하지 않습니다.')
    else:
        unit = None
    separators = layout.get('semicolon_separators')
    wants_no_semis = None
    if type(separators) is int and separators >= 0:
        wants_no_semis = separators == 0
    histogram = layout.get('blank_lines_between_code_histogram')
    limit = None
    if isinstance(histogram, dict) and histogram:
        sizes = []
        for key, count in histogram.items():
            if isinstance(key, str) and key.isdecimal() and type(count) is int and count > 0:
                sizes.append(int(key))
        if sizes:
            limit = max(sizes)
    return kind, unit, wants_no_semis, limit


def apply_saved_formatting_style(
    code: str, profile: dict[str, Any] | None
) -> tuple[str, list[str], list[str]]:
    """Return (code, applied_rules, warnings) using static AST preservation.

    No `exec`, import of user code, or runtime execution is performed here.
    Indentation, safe semicolon splits and excess empty lines are supported.
    Only adjacent simple assignments are joined; general statement joining and
    reflowing expressions inside brackets are deferred.
    """
    rules: list[str] = []
    warnings: list[str] = []
    if profile is None:
        return code, rules, warnings
    try:
        kind, unit, wants_no_semis, blank_limit = _profile_preference(profile)
        original_ast = _ast_signature(code)
        _tokens(code)
    except (FormattingProfileError, SyntaxError, tokenize.TokenError, IndentationError, TypeError, ValueError) as exc:
        return code, rules, [f'서식 자동 적용 생략: {exc}']

    result = code

    def try_edit(candidate: str, label: str) -> None:
        nonlocal result
        if candidate == result:
            return
        if _ast_signature(candidate) == original_ast:
            result = candidate
            rules.append('적용 완료: ' + label)
        else:
            warnings.append(label + ' 적용 시 Python 구문 구조가 달라져 변경을 취소했습니다.')

    try:
        if kind in ('spaces', 'tabs') and unit is not None:
            try_edit(_indent_lines(result, kind, unit), f'저장된 들여쓰기 서식({"스페이스" if kind == "spaces" else "탭"}, {unit}열)')
        elif kind == 'mixed':
            warnings.append('저장된 스타일의 들여쓰기가 혼용되어 자동 변환하지 않았습니다.')

        if wants_no_semis is True:
            try_edit(_semicolon_lines(result), '한 줄의 여러 문장을 문장별 줄바꿈으로 분리')
        elif wants_no_semis is False:
            combined = _combine_simple_assignments(result)
            if combined == result:
                warnings.append('한 줄 배치 스타일이지만 안전하게 결합할 인접 대입문이 없어 생략했습니다.')
            else:
                try_edit(combined, '인접한 단순 대입문을 한 줄로 결합')

        if blank_limit is not None:
            try_edit(_remove_excess_blank_lines(result, blank_limit), '과도한 연속 빈 줄 축소')
    except (SyntaxError, tokenize.TokenError, IndentationError, TypeError, ValueError) as exc:
        warnings.append('서식 자동 적용 중 분석 오류로 남은 변경을 생략했습니다: ' + type(exc).__name__)

    # CAPSTONE_LINEBREAK_STYLE_V1: 구체적인 문맥별 빈 줄 및 괄호 내부 줄바꿈.
    # 이전에 저장한 스타일에는 추가 데이터가 없으므로 기존처럼 동작합니다.
    try:
        from app.services.style_linebreak_service import (
            apply_context_blank_lines,
            apply_bracket_linebreaks,
        )
        layout = profile.get("line_layout", {})
        if isinstance(layout, dict):
            try_edit(
                apply_context_blank_lines(result, layout),
                "저장된 함수·제어문 주변 빈 줄 간격",
            )
            # 먼저 적용된 들여쓰기 단위 또는 현재 코드의 기본 단위를 이용합니다.
            bracket_unit = ("\t" if kind == "tabs" else
                            " " * unit if kind == "spaces" and unit else " " * 4)
            try_edit(
                apply_bracket_linebreaks(result, layout, bracket_unit),
                "저장된 괄호 안 여러 줄 작성 방식",
            )
    except (SyntaxError, tokenize.TokenError, IndentationError, TypeError,
            ValueError, IndexError) as exc:
        warnings.append(
            "줄바꿈 서식 처리 오류로 해당 변경을 생략했습니다: "
            + type(exc).__name__
        )

    # Final fence against accidental algorithmic bugs in individual steps.
    if not _same_ast(code, result):
        return code, [], warnings + ['최종 Python 구문 구조 검증 실패로 서식 변경을 모두 취소했습니다.']
    return result, rules, warnings
