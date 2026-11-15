"""Install backend-only final output comment filtering safely.

Run at the repository root:
    python backend/tools/install_style_output_comment_cleanup.py --check
    python backend/tools/install_style_output_comment_cleanup.py

Requires the unchanged 832f1b4 version of backend/app/api/routes/style_apply.py.
Accepts both exact LF (Git) and CRLF (Windows) checkout encodings.
Preserves the original line-ending style when patching.
No frontend files and no previously installed transform files are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_ROOT = Path(__file__).resolve().parent / 'style_output_cleanup_payload'
BASE_COMMIT = '832f1b4dc7884cdb70a7558b039f8b70621043eb'
ROUTE_REL = Path('backend/app/api/routes/style_apply.py')
SERVICE_REL = Path('backend/app/services/style_output_comment_service.py')
TEST_REL = Path('backend/tests/test_style_output_comment_service.py')
INTEGRATION_REL = Path('backend/tests/test_style_output_comment_api_integration.py')
AUDIT_REL = Path('backend/tools/audit_transform_three_patterns.py')
MARK = '# CAPSTONE_STYLE_OUTPUT_COMMENT_CLEANUP_V1'

IMPORT_ANCHOR = 'from app.services.execution_validation_service import verify_execution_equivalence\n'
IMPORT_PATCH = IMPORT_ANCHOR + (
    'from app.services.style_output_comment_service import strip_style_output_comments\n'
)
END_ANCHOR = '''        return StyleApplyResponse(
            success=True,
            original_code=request.code,
'''
POSTPROCESS = '''        # CAPSTONE_STYLE_OUTPUT_COMMENT_CLEANUP_V1: only code shown on Style Apply is cleaned.
        # Remove comments and independent string expressions even when no
        # style action changed the Python AST or the earlier action rolled back.
        displayed_code = strip_style_output_comments(transformed_code)
        if displayed_code != transformed_code:
            transformed_code = displayed_code
            # Final verification must describe the exact displayed code.
            # Removing actual docstrings may change __doc__; never silently
            # label such output equivalent or revert the requested cleanup.
            try:
                cleanup_check = verify_execution_equivalence(
                    original_code=request.code,
                    transformed_code=transformed_code,
                    function_cases=function_cases,
                )
            except Exception as cleanup_error:
                cleanup_check = None
                warnings.append(
                    "주석 제거 후 최종 실행 검증 오류: "
                    + type(cleanup_error).__name__
                )
            cleanup_valid = isinstance(cleanup_check, dict)
            if cleanup_valid:
                cleanup_status = cleanup_check.get("status")
                cleanup_eq = cleanup_check.get("equivalent")
                cleanup_valid = (
                    cleanup_status in ("equivalent", "different", "not_verified")
                    and ((cleanup_status == "equivalent" and cleanup_eq is True)
                         or (cleanup_status == "different" and cleanup_eq is False)
                         or (cleanup_status == "not_verified" and cleanup_eq is None))
                    and isinstance(cleanup_check.get("original"), dict)
                    and isinstance(cleanup_check.get("transformed"), dict)
                )
            if cleanup_valid:
                execution_verification = cleanup_check
                if cleanup_check["status"] == "different":
                    warnings.append(
                        "주석 및 독립 문자열 제거 후 실행 결과가 달라졌습니다. "
                        "독스트링(__doc__)을 참조하는 코드인지 확인해 주세요."
                    )
                elif cleanup_check["status"] == "not_verified":
                    warnings.append(
                        "주석 제거 후 최종 코드의 실행 동등성은 확인되지 않았습니다."
                    )
            else:
                execution_verification = None
                warnings.append(
                    "주석 제거 후 최종 코드의 실행 결과를 확인하지 못했습니다."
                )
            summary = (summary or "").replace(
                "최종 코드 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                "주석 제거 후 최종 코드의 실행 결과 비교를 시도했습니다.",
            ) + (
                " 최종 표시 코드에서 주석과 독립 문자열 설명문을 제외했습니다."
            )

'''


def _git_original(root: Path) -> bytes:
    result = subprocess.run(
        ['git', 'show', f'{BASE_COMMIT}:{ROUTE_REL.as_posix()}'],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            '기준 커밋 832f1b4에서 style_apply.py를 찾을 수 없습니다. '
            '프로젝트 원본 저장소 경로를 확인해 주세요.'
        )
    return result.stdout


def _patched_route(original: bytes) -> bytes:
    bom = b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b''
    content = original[len(bom):]
    crlf = b'\r\n' in content
    code = content.decode('utf-8').replace('\r\n', '\n')
    if code.count(IMPORT_ANCHOR) != 1 or code.count(END_ANCHOR) != 1:
        raise RuntimeError('API 경로의 설치 위치가 기준 버전과 다릅니다.')
    code = code.replace(IMPORT_ANCHOR, IMPORT_PATCH, 1)
    code = code.replace(END_ANCHOR, POSTPROCESS + END_ANCHOR, 1)
    compile(code, ROUTE_REL.as_posix(), 'exec')
    return bom + (code.replace('\n', '\r\n') if crlf else code).encode('utf-8')


def _verify_git(root: Path) -> None:
    result = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError('Git 프로젝트 폴더를 찾지 못했습니다.')
    if Path(result.stdout.decode('utf-8').strip()).resolve() != root.resolve():
        raise RuntimeError('프로젝트 최상위 경로에서 설치기를 실행해 주세요.')


def install(*, check_only: bool) -> None:
    root = SOURCE_ROOT
    _verify_git(root)
    route_path = root / ROUTE_REL
    baseline_lf = _git_original(root)
    # git show emits the exact committed LF bytes. Windows checkouts may
    # convert those LF line endings to CRLF. These are identical Python code,
    # but their SHA256 checksums differ. Accept ONLY the two exact versions.
    # Never accept a semantically different or manually modified source file.
    baseline_crlf = baseline_lf.replace(b'\n', b'\r\n')
    patched_lf = _patched_route(baseline_lf)
    patched_crlf = _patched_route(baseline_crlf)
    current = route_path.read_bytes()

    if current == baseline_lf:
        desired = patched_lf
    elif current == baseline_crlf:
        desired = patched_crlf
    elif current in (patched_lf, patched_crlf):
        desired = current  # Idempotent: already installed on either platform.
    else:
        raise RuntimeError(
            '기존 style_apply.py가 기준 버전과 다릅니다. 덮어쓰지 않았습니다.\n'
            f'현재 SHA256: {hashlib.sha256(current).hexdigest()}\n'
            f'기준 LF SHA256: {hashlib.sha256(baseline_lf).hexdigest()}\n'
            f'기준 CRLF SHA256: {hashlib.sha256(baseline_crlf).hexdigest()}\n'
            '줄바꿈 이외에 코드 변경이 있을 수 있으므로 강제 설치하지 마세요.'
        )

    new_files = (SERVICE_REL, TEST_REL, INTEGRATION_REL, AUDIT_REL)
    for rel in new_files:
        source = PAYLOAD_ROOT / (rel.name + '.source')
        destination = root / rel
        if not source.is_file():
            raise RuntimeError(f'설치 파일이 누락됐습니다: {rel}')
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise RuntimeError(f'기존 파일과 충돌하여 중단했습니다: {rel}')

    changes = []
    if current != desired:
        changes.append((route_path, desired))
    for rel in new_files:
        src = PAYLOAD_ROOT / (rel.name + '.source')
        dst = root / rel
        if not dst.exists():
            changes.append((dst, src.read_bytes()))

    if check_only:
        print(f'검사 통과: {len(changes)}개 파일 설치 예정, frontend 파일 변경 없음')
        return
    if not changes:
        print('이미 설치된 상태입니다. 변경 없음')
        return

    # Back up every existing file before any replacement.
    backup = root / '.git' / 'capstone_style_output_comment_backup' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    for destination, _data in changes:
        if destination.exists():
            target = backup / destination.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, target)
    for destination, data in changes:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        print('설치:', destination.relative_to(root))
    print('적용 완료. 백업:', backup)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        install(check_only=args.check)
    except (OSError, UnicodeError, RuntimeError, subprocess.SubprocessError) as e:
        print('설치 중단:', e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
