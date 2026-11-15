"""Conservative, independent function/method transforms in longer Python files.

Runs *after* existing whole-program style actions and *before* their execution
verification. Only one additional, allowlisted action may edit each scope;
unchanged code (including comments and formatting) is left byte-for-byte intact.
No code is executed by this module. The caller must verify the final whole file.
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
import io
import tokenize
from typing import Callable

MIN_LONG_CODE_LINES = 80
MAX_LONG_CODE_LINES = 2000
MAX_SCOPES = 80

# Every action here operates on a function body without requiring other
# enclosing definitions. Sensitive moves (imports, decorators, global names,
# function creation, attribute access, etc.) are deliberately excluded.
SCOPED_SAFE_ACTIONS = frozenset({
    'create_safe_comprehension_collection',
    'create_safe_append_collection',
    'create_safe_dict_comprehension',
    'create_safe_dict_loop',
    'create_safe_set_comprehension',
    'create_safe_set_loop',
    'create_if_statement',
    'create_conditional_expression',
    'create_return_structure',
})

# These constructs depend on runtime / enclosing context or can affect the
# semantics of source-level code rewriting (e.g. locals() observing variables).
_DYNAMIC_NAMES = frozenset({
    'locals', 'globals', 'vars', 'dir', 'eval', 'exec', 'compile',
    'inspect', 'sys', 'frame', '__import__',
})
_UNSAFE_SCOPE_NODES = (
    ast.Global, ast.Nonlocal, ast.Yield, ast.YieldFrom, ast.Await,
    ast.AsyncFor, ast.AsyncWith,
)


@dataclass(frozen=True)
class Scope:
    start_line: int  # 1-indexed, inclusive
    end_line: int    # 1-indexed, inclusive
    indent: str
    label: str
    node: ast.FunctionDef


def _safe_scopes(source: str) -> list[Scope]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    scopes: list[Scope] = []

    def add(node: ast.AST, label: str):
        if not isinstance(node, ast.FunctionDef):
            return
        if node.decorator_list or node.type_comment or node.end_lineno is None:
            return
        if not (1 <= node.lineno <= node.end_lineno <= len(lines)):
            return
        line = lines[node.lineno - 1]
        indent = line[:len(line) - len(line.lstrip(' \t'))]
        if not line[len(indent):].startswith('def '):
            return
        # A standalone function is never rewritten if it contains dynamic
        # scope inspection, nested definitions, generators or unsafe scopes.
        for child in ast.walk(node):
            if isinstance(child, _UNSAFE_SCOPE_NODES):
                return
            if isinstance(child, (ast.ClassDef, ast.AsyncFunctionDef)):
                return
            if child is not node and isinstance(child, ast.FunctionDef):
                return
            if isinstance(child, ast.Name) and child.id in _DYNAMIC_NAMES:
                return
            if isinstance(child, (ast.Import, ast.ImportFrom)) and (
                (isinstance(child, ast.Import) and any(a.name.split('.')[0] in _DYNAMIC_NAMES for a in child.names))
                or (isinstance(child, ast.ImportFrom) and (child.module or '').split('.')[0] in _DYNAMIC_NAMES)
            ):
                return
        scopes.append(Scope(node.lineno, node.end_lineno, indent, label, node))

    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef):
            add(stmt, stmt.name)
        elif isinstance(stmt, ast.ClassDef):
            # Class body is not a standard function scope. Only its direct,
            # undecorated instance/static methods are eligible.
            for member in stmt.body:
                if isinstance(member, ast.FunctionDef):
                    add(member, stmt.name + '.' + member.name)
    return scopes


def _contains_multiline_string(text: str) -> bool:
    try:
        return any(
            token.type == tokenize.STRING and token.start[0] != token.end[0]
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
        )
    except (tokenize.TokenError, IndentationError):
        return True


def _significant_source_tokens(source: str) -> tuple[Counter, Counter] | None:
    """Keep original comment text and string token spellings unchanged."""
    try:
        comments: Counter[str] = Counter()
        strings: Counter[str] = Counter()
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                comments[token.string] += 1
            elif token.type == tokenize.STRING:
                strings[token.string] += 1
        return comments, strings
    except (tokenize.TokenError, IndentationError):
        return None


def _extract_scope(lines: list[str], scope: Scope) -> str | None:
    chunk = lines[scope.start_line - 1:scope.end_line]
    dedented: list[str] = []
    for line in chunk:
        if not line.strip():
            dedented.append(line)
        elif line.startswith(scope.indent):
            dedented.append(line[len(scope.indent):])
        else:
            return None
    text = ''.join(dedented)
    if _contains_multiline_string(text):
        return None
    return text


def _parse_one_function(source: str) -> ast.FunctionDef | None:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return None
    return tree.body[0]


def _same_signature(a: ast.FunctionDef, b: ast.FunctionDef) -> bool:
    return (
        a.name == b.name
        and not b.decorator_list
        and ast.dump(a.args, include_attributes=False)
            == ast.dump(b.args, include_attributes=False)
        and (ast.dump(a.returns, include_attributes=False) if a.returns else None)
            == (ast.dump(b.returns, include_attributes=False) if b.returns else None)
        and ast.get_docstring(a) == ast.get_docstring(b)
    )


def _reindent(source: str, indent: str, trailing_newline: bool) -> str:
    output = ''.join(indent + line if line.strip() else line
                     for line in source.splitlines(keepends=True))
    if trailing_newline and output and not output.endswith(('\n', '\r')):
        output += '\n'
    if not trailing_newline:
        output = output.rstrip('\r\n')
    return output


def apply_scoped_style_to_large_code(
    *,
    code: str,
    style: dict,
    compare_style: Callable[..., dict],
    build_plan: Callable[[dict], dict],
    get_transformer: Callable[[str], Callable[[str], str] | None],
) -> tuple[str, list[dict], list[str]]:
    """Return (new_source, successfully-applied actions, warnings).

    Independent local style differences can reveal missing patterns which
    whole-program tag-set comparison misses. Existing whole-code transforms
    are not replaced. Whole-program runtime checking stays the responsibility
    of style_apply_service after this stage finishes.
    """
    number_of_lines = len(code.splitlines())
    if number_of_lines < MIN_LONG_CODE_LINES:
        return code, [], []
    if number_of_lines > MAX_LONG_CODE_LINES:
        return code, [], ['긴 코드 분석은 현재 최대 2,000줄로 제한됩니다.']
    try:
        scopes = _safe_scopes(code)
    except (SyntaxError, ValueError):
        return code, [], []
    if len(scopes) > MAX_SCOPES:
        return code, [], ['함수·메서드가 80개를 초과하여 범위별 추가 변환을 생략했습니다.']

    # Bottom-up replacement preserves original line indexes for earlier units.
    output_lines = code.splitlines(keepends=True)
    applied: list[dict] = []
    warnings: list[str] = []
    for scope in reversed(scopes):
        snippet = _extract_scope(output_lines, scope)
        if snippet is None:
            continue
        original_ast = _parse_one_function(snippet)
        original_tokens = _significant_source_tokens(snippet)
        if original_ast is None or original_tokens is None:
            continue
        try:
            local_diff = compare_style(style=style, code=snippet)
            local_plan = build_plan(local_diff)
        except Exception:
            # For unsupported functions the existing whole-file logic remains.
            continue
        if not isinstance(local_plan, dict):
            continue
        for item in local_plan.get('actions', []):
            if not isinstance(item, dict):
                continue
            action = item.get('action')
            if action not in SCOPED_SAFE_ACTIONS:
                continue
            transform = get_transformer(action)
            if transform is None:
                continue
            try:
                candidate = transform(snippet)
            except Exception:
                continue
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            updated_ast = _parse_one_function(candidate)
            if updated_ast is None or not _same_signature(original_ast, updated_ast):
                continue
            if (ast.dump(original_ast, include_attributes=False)
                    == ast.dump(updated_ast, include_attributes=False)):
                continue
            if _significant_source_tokens(candidate) != original_tokens:
                continue
            original_chunk = ''.join(output_lines[scope.start_line - 1:scope.end_line])
            replacement = _reindent(
                candidate, scope.indent,
                original_chunk.endswith(('\n', '\r')),
            )
            # Keep CRLF source files CRLF without altering string literals:
            # multiline literal units are not eligible for this operation.
            if '\r\n' in original_chunk:
                replacement = replacement.replace('\r\n', '\n').replace('\n', '\r\n')
            trial_lines = (
                output_lines[:scope.start_line - 1]
                + [replacement]
                + output_lines[scope.end_line:]
            )
            try:
                ast.parse(''.join(trial_lines))
            except (SyntaxError, ValueError):
                continue
            output_lines = trial_lines
            applied.append({
                'tag': str(item.get('tag') or ''),
                'action': action,
                'scope': scope.label,
                'reason': str(item.get('reason') or ''),
            })
            # A single committed action per scope prevents same-scope rules
            # from undoing each other; different functions are independent.
            break
    if applied:
        warnings.append(
            '긴 코드의 함수·메서드별 추가 변환은 실행 결과 및 함수 테스트를 '
            '통해 동등성이 확인되는 경우에만 최종 유지합니다.'
        )
    return ''.join(output_lines), list(reversed(applied)), warnings
