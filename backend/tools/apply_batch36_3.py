"""Apply Batch36-3's three reviewable source patches, idempotently.

Do not overwrite the user's local source versions: check all anchors before
writing any file. The service/test/audit files are supplied separately in ZIP.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

PATCHES = {
    'app/services/style_apply_service.py': [
        (
            'from app.services.style_action_diagnostic_service import build_transform_diagnostics',
            'from app.services.style_action_diagnostic_service import build_transform_diagnostics\n'
            'from app.services.style_action_preflight_service import screen_action_candidate\n'
            '# CAPSTONE_BATCH36_3_PREFLIGHT_IMPORT_V1',
        ),
        (
            '''    applied_rules: list[str],
    warnings: list[str],
) -> tuple[str, dict]:''',
            '''    applied_rules: list[str],
    warnings: list[str],
    preflight_enabled: bool = False,
) -> tuple[str, dict]:''',
        ),
        (
            '''    before = code
    try:
        after = transform_func(code)''',
            '''    # CAPSTONE_BATCH36_3_PREFLIGHT_V1: inspect current, sequentially
    # transformed code, never original input, before calling narrow transform.
    if preflight_enabled:
        preflight = screen_action_candidate(action, code)
        if preflight is not None:
            result["status"] = "skipped_shape_preflight"
            result["preflight_reason_code"] = preflight["reason_code"]
            result["preflight_reason"] = preflight["reason"]
            return code, result

    before = code
    try:
        after = transform_func(code)''',
        ),
        (
            '''            applied_rules=applied_rules,
            warnings=warnings,
        )''',
            '''            applied_rules=applied_rules,
            warnings=warnings,
            preflight_enabled=(isinstance(metric_info, dict)
                               and metric_info.get("status") == "current_complete"
                               and metric_info.get("stored_version") == 1),
        )''',
        ),
    ],
    'app/services/style_action_diagnostic_service.py': [
        (
            '''    "no_safe_pattern": ("no_safe_pattern", "대상 코드에서 변환기의 안전 조건을 만족하는 패턴을 찾지 못했습니다."),''',
            '''    "no_safe_pattern": ("no_safe_pattern", "대상 코드에서 변환기의 안전 조건을 만족하는 패턴을 찾지 못했습니다."),
    "skipped_shape_preflight": ("missing_required_ast_shape", "필수 AST 구조가 없어 변환기를 호출하지 않았습니다."),  # CAPSTONE_BATCH36_3_DIAG_V1''',
        ),
        (
            '''    result = {
        "tag": tag, "action": action, "status": status,
        "reason_code": reason_code, "reason": reason,
    }''',
            '''    if status == "skipped_shape_preflight":
        reason_code = raw.get("preflight_reason_code") or reason_code
        reason = raw.get("preflight_reason") or reason
    result = {
        "tag": tag, "action": action, "status": status,
        "reason_code": reason_code, "reason": reason,
    }''',
        ),
    ],
    'app/services/style_action_outcome_service.py': [
        (
            '    "no_safe_pattern": ("skipped", "적용할 안전한 코드 패턴 없음"),',
            '    "no_safe_pattern": ("skipped", "적용할 안전한 코드 패턴 없음"),\n'
            '    "skipped_shape_preflight": ("skipped", "필수 문법 형태가 없어 변환기 실행 생략"),  # CAPSTONE_BATCH36_3_OUTCOME_V1',
        ),
    ],
    'app/services/improvement/safe_structural_patterns_service.py': [
        (
            '''def _convert_attribute(tree: ast.Module, stmt: ast.stmt, direction: str) -> list[ast.stmt] | None:''',
            '''def _change_wrapped_print_call(tree: ast.Module, stmt: ast.stmt, index: int) -> list[ast.stmt] | None:
    """CAPSTONE_BATCH36_3_NESTED_KEYWORD_V1: closed print(fn(literals)) form.

    Changing evaluation order is dangerous with side-effectful arguments.
    Only one direct print of a statically defined, stable local function with
    primitive constant arguments is eligible; all existing safety checks and
    comment-preserving edit routines remain in force.
    """
    if (len(tree.body) != 2 or index != 1 or not isinstance(tree.body[0], ast.FunctionDef)
            or not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call)):
        return None
    outer = stmt.value
    if (not isinstance(outer.func, ast.Name) or outer.func.id != 'print'
            or _is_shadowed(tree, 'print') or len(outer.args) != 1 or outer.keywords):
        return None
    inner = outer.args[0]
    if (not isinstance(inner, ast.Call) or not isinstance(inner.func, ast.Name)
            or inner.keywords or not inner.args):
        return None
    if not all(isinstance(arg, ast.Constant) and type(arg.value) in
               (int, float, bool, str, type(None)) for arg in inner.args):
        return None
    signature = _module_function(tree, inner.func.id, index)
    if signature is None or len(inner.args) != len(signature):
        return None
    updated = copy.deepcopy(stmt)
    nested = updated.value.args[0]
    nested.keywords = [ast.keyword(arg=name, value=copy.deepcopy(value))
                       for name, value in zip(signature, inner.args)]
    nested.args = []
    return [updated]


def _convert_attribute(tree: ast.Module, stmt: ast.stmt, direction: str) -> list[ast.stmt] | None:''',
        ),
        (
            '''                        if signature is not None:
                            replacements = _change_call(stmt, signature, direction)''',
            '''                        if signature is not None:
                            replacements = _change_call(stmt, signature, direction)
                if replacements is None and direction == 'to_keywords':
                    replacements = _change_wrapped_print_call(tree, stmt, i)''',
        ),
    ],
}

MARKERS = {
    'app/services/style_apply_service.py': 'CAPSTONE_BATCH36_3_PREFLIGHT_V1',
    'app/services/style_action_diagnostic_service.py': 'CAPSTONE_BATCH36_3_DIAG_V1',
    'app/services/style_action_outcome_service.py': 'CAPSTONE_BATCH36_3_OUTCOME_V1',
    'app/services/improvement/safe_structural_patterns_service.py': 'CAPSTONE_BATCH36_3_NESTED_KEYWORD_V1',
}


def _patch(filename: str, raw: bytes) -> tuple[bytes, str]:
    newline = '\r\n' if b'\r\n' in raw else '\n'
    source = raw.decode('utf-8').replace('\r\n', '\n')
    if MARKERS[filename] in source:
        if source.count(MARKERS[filename]) != 1:
            raise RuntimeError('부분 적용/중복 마커 감지: ' + filename)
        return raw, 'already_applied'
    for old, new in PATCHES[filename]:
        count = source.count(old)
        if count != 1:
            raise RuntimeError(f'앵커 불일치({count}개): {filename}: {old[:65]!r}')
        source = source.replace(old, new, 1)
    if source.count(MARKERS[filename]) != 1:
        raise RuntimeError('마커 검증 실패: ' + filename)
    ast.parse(source, filename=filename)
    return source.replace('\n', newline).encode('utf-8'), 'ready'


def install(root: Path, apply: bool) -> dict[str, str]:
    staged = {}
    status = {}
    for filename in PATCHES:
        path = root / filename
        if not path.is_file():
            raise RuntimeError('기존 파일을 찾지 못했습니다: ' + str(path))
        data, state = _patch(filename, path.read_bytes())
        staged[path] = data
        status[filename] = state
    if apply:
        for path, data in staged.items():
            if status[str(path.relative_to(root)).replace('\\', '/')] == 'ready':
                path.write_bytes(data)
    return status


def main(argv=None):
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        statuses = install(ROOT, apply=args.apply)
    except (RuntimeError, UnicodeError, OSError) as exc:
        print('36-3 적용 중단:', exc, file=sys.stderr)
        return 2
    for filename, status in statuses.items():
        print(f'36-3 {filename}: {status}')
    if args.apply:
        print('36-3 서비스 패치 적용 완료')
    else:
        print('36-3 서비스 패치 가능 여부 확인 완료 (파일 변경 없음)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
