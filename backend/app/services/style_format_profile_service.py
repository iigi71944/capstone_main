"""Python 소스의 실제 서식 습관을 동적으로 추출한다.

서식 특성은 문법/개념 태그와 분리한다. 원본 코드를 수정하지 않으며
문법에 필수인 블록 들여쓰기는 임의로 추측하지 않는다.
"""

from __future__ import annotations

import ast
from collections import Counter
import io
import tokenize
from typing import Any


STYLE_PROFILE_VERSION = 1


def _primary(counter: Counter) -> Any:
    """빈 관측에서 고정된 기본 서식을 강요하지 않는다."""
    if not counter:
        return None
    # 관측 횟수가 동률이면 작은 수 / 사전순을 택한다.
    return sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))[0][0]


def _counts(counter: Counter) -> dict[str, int]:
    return {str(key): value for key, value in sorted(counter.items(), key=lambda item: str(item[0]))}


def _standalone_string_starts(tree: ast.AST, lines: list[str]) -> set[tuple[int, int]]:
    """독스트링과 독립적인 문자열 표현식의 시작 위치 (line, char col)."""
    ignored = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            continue
        constant = node.value
        lineno = getattr(constant, "lineno", 0)
        if not (1 <= lineno <= len(lines)):
            continue
        # ast.col_offset은 UTF-8 바이트, tokenize 열은 문자 인덱스다.
        raw = lines[lineno - 1].encode("utf-8")[:constant.col_offset]
        ignored.add((lineno, len(raw.decode("utf-8", errors="ignore"))))
    return ignored


def extract_formatting_style(code: str) -> dict[str, Any]:
    """유효한 Python 소스를 관측하여 JSON 직렬화 가능한 프로필을 반환한다.

    고정된 '표준 4칸' 식 프리셋은 만들지 않는다. 근거가 없는 항목은
    None / 빈 분포로 반환하므로 짧은 코드에서도 허위 추론하지 않는다.
    """
    if not isinstance(code, str):
        raise TypeError("code는 문자열이어야 합니다.")
    tree = ast.parse(code)
    lines = code.splitlines(keepends=True)
    ignored_strings = _standalone_string_starts(tree, lines)

    tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    indent_modes: Counter = Counter()
    indent_steps: Counter = Counter()
    indents = [0]
    statement_lines: set[int] = set()
    code_lines: set[int] = set()
    blank_gap_histogram: Counter = Counter()
    continuation_lines = 0
    multiline_statements = 0
    semicolon_count = 0
    logical_count = 0
    visible_in_statement = False
    statement_first_line = None
    bracket_depth = 0
    trailing_comma_multiline = 0
    brackets_with_newlines = 0
    bracket_newlines_stack: list[bool] = []
    last_meaningful_token = None
    explicit_backslash_lines = 0
    current_soft_linebreaks = 0

    def is_visible_token(tok: tokenize.TokenInfo) -> bool:
        if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER,
                        tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                        tokenize.INDENT, tokenize.DEDENT):
            return False
        if tok.type == tokenize.STRING and tok.start in ignored_strings:
            return False
        return bool(tok.string.strip())

    for tok in tokens:
        if tok.type == tokenize.INDENT:
            raw = tok.string
            if "\t" in raw and " " in raw:
                indent_modes["mixed"] += 1
            elif "\t" in raw:
                indent_modes["tabs"] += 1
            elif raw:
                indent_modes["spaces"] += 1
            visual_width = len(raw.expandtabs(8))
            step = visual_width - indents[-1]
            if step > 0:
                indent_steps[step] += 1
            indents.append(visual_width)
        elif tok.type == tokenize.DEDENT:
            if len(indents) > 1:
                indents.pop()

        if tok.type == tokenize.NL and bracket_depth > 0:
            # 주석/공백만 있는 줄은 명시적 줄바꿈 취향으로 세지 않는다.
            if tok.line.strip() and not tok.line.lstrip().startswith("#"):
                continuation_lines += 1
                current_soft_linebreaks += 1
                if bracket_newlines_stack:
                    bracket_newlines_stack[-1] = True

        if tok.type == tokenize.NEWLINE:
            if visible_in_statement:
                logical_count += 1
                statement_lines.add(tok.start[0])
                # 괄호 또는 명시적 backslash에 의한 여러 물리 줄
                if statement_first_line is not None and tok.start[0] > statement_first_line:
                    # multiline 문자열 리터럴 자체는 서식 줄바꿈으로 보지 않음
                    if current_soft_linebreaks or any(
                        lines[number - 1].rstrip().endswith("\\")
                        for number in range(statement_first_line, tok.start[0])
                    ):
                        multiline_statements += 1
            visible_in_statement = False
            statement_first_line = None
            current_soft_linebreaks = 0

        if not is_visible_token(tok):
            continue
        if statement_first_line is None:
            statement_first_line = tok.start[0]
        visible_in_statement = True
        code_lines.add(tok.start[0])
        prior_meaningful_token = last_meaningful_token
        last_meaningful_token = tok

        if tok.type == tokenize.OP:
            if tok.string == ";":
                semicolon_count += 1
            elif tok.string in "([{":
                bracket_depth += 1
                bracket_newlines_stack.append(False)
            elif tok.string in ")]}" and bracket_depth > 0:
                bracket_depth -= 1
                had_newline = bracket_newlines_stack.pop()
                if had_newline:
                    brackets_with_newlines += 1
                    if prior_meaningful_token is not None and prior_meaningful_token.string == ",":
                        trailing_comma_multiline += 1

    # 역슬래시 줄 연속: 인용된 문자열 안의 백슬래시를 오인하지 않도록
    # 실제 코드 토큰이 존재한 줄만 살핀다. 매우 복잡한 문자열은 추론 대상에서 제외.
    for number in sorted(code_lines):
        line = lines[number - 1] if number <= len(lines) else ""
        if line.rstrip().endswith("\\"):
            # 실제 역슬래시 연속문인지 tokenize는 물리 NL을 별도 생성하지 않음.
            explicit_backslash_lines += 1

    # 위에서 토큰 처리 중 사용한 backslash 카운터는 최종 물리 라인 관측치로 계산.
    # 괄호 안 줄바꿈과 explicit backslash를 각각 독립적인 정보로 노출한다.
    for a, b in zip(sorted(code_lines), sorted(code_lines)[1:]):
        if b <= a + 1:
            blank_gap_histogram[0] += 1
            continue
        gap = sum(1 for idx in range(a + 1, b) if not lines[idx - 1].strip())
        blank_gap_histogram[gap] += 1

    endings = Counter()
    for number in sorted(code_lines):
        line = lines[number - 1]
        if line.endswith("\r\n"):
            endings["crlf"] += 1
        elif line.endswith("\n"):
            endings["lf"] += 1
        elif line.endswith("\r"):
            endings["cr"] += 1

    line_type = _primary(indent_modes)
    common_step = _primary(indent_steps)
    # 줄 연속 표현을 나타내는 정량적 비율; 특정 코드 스타일을 억지로 명명하지 않음
    result = {
        "version": STYLE_PROFILE_VERSION,
        "indentation": {
            "kind": line_type,
            "unit_columns": common_step,
            "indentation_occurrences": sum(indent_modes.values()),
            "kind_histogram": _counts(indent_modes),
            "unit_histogram": _counts(indent_steps),
        },
        "line_layout": {
            "logical_statements": logical_count,
            "semicolon_separators": semicolon_count,
            "multiple_statements_on_line": semicolon_count > 0,
            "multiline_statements": multiline_statements,
            "parenthesized_line_breaks": continuation_lines,
            "multiline_bracket_groups": brackets_with_newlines,
            "multiline_bracket_groups_with_trailing_comma": trailing_comma_multiline,
            "explicit_backslash_line_breaks": explicit_backslash_lines,
            "blank_lines_between_code_histogram": _counts(blank_gap_histogram),
            "typical_blank_lines_between_code": _primary(blank_gap_histogram),
            "physical_code_lines": len(code_lines),
        },
        "line_endings": {
            "preferred": _primary(endings),
            "histogram": _counts(endings),
        },
    }
    # CAPSTONE_LINEBREAK_STYLE_V1: 각 줄바꿈의 *위치*까지 보존합니다.
    from app.services.style_linebreak_service import extract_linebreak_preferences
    result["line_layout"].update(extract_linebreak_preferences(code))
    return result
