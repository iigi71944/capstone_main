"""Restore execution results for formatting-only style applications.

Patches *only* backend/app/api/routes/style_apply.py from the previously
installed saved-formatting V1 integration.  The old integration remains intact.
This uses complete preflight and an immutable backup, including idempotence.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
import tempfile

V1 = "CAPSTONE_SAVED_FORMAT_APPLY_V1"
V2 = "CAPSTONE_FORMATTING_EXECUTION_VERIFY_V2"


class InstallationError(RuntimeError):
    pass


def _single(source: str, token: str, label: str) -> None:
    count = source.count(token)
    if count != 1:
        raise InstallationError(f"{label}: 연결 위치를 1개 예상했지만 {count}개입니다. 기존 소스를 변경하지 않습니다.")


def patch_route(source: str) -> str:
    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise InstallationError("기존 스타일 적용 라우트의 Python 문법이 올바르지 않습니다.") from exc

    if V2 in source:
        # A partial/stale edit must not be mistaken for a completed install.
        if (
            source.count(V2) != 2
            or "from app.services.execution_validation_service import verify_execution_equivalence\n" not in source
            or "        code_before_format = transformed_code\n" not in source
            or "        if formatting_profile is not None and transformed_code != code_before_format:\n" not in source
        ):
            raise InstallationError("서식 실행 결과 수정이 일부만 적용되어 있습니다. 수동 확인이 필요합니다.")
        return source
    if V1 not in source:
        raise InstallationError("선행 서식 적용 기능(V1)이 설치되지 않았습니다.")

    import_anchor = "from app.services.style_format_apply_service import apply_saved_formatting_style\n"
    profile_anchor = "        formatting_profile = request.style.formatting_style\n"
    return_anchor = "        return StyleApplyResponse(\n            success=True,"
    for label, anchor in [
        ("서식 적용 import", import_anchor),
        ("서식 적용 프로필", profile_anchor),
        ("성공 응답", return_anchor),
    ]:
        _single(source, anchor, label)

    source = source.replace(
        import_anchor,
        import_anchor + "from app.services.execution_validation_service import verify_execution_equivalence\n",
        1,
    )
    # Capture the semantic transformation's result before optional formatting.
    # Its existing verifier, warnings and rule list are preserved separately.
    capture = (
        f"        # {V2}: 서식 변경 전 상태 기록\n"
        "        code_before_format = transformed_code\n"
        "        rules_before_format = len(applied_rules)\n"
        "        summary_before_format = summary\n"
    )
    source = source.replace(profile_anchor, capture + profile_anchor, 1)

    after_format = f'''        # {V2}: 화면에 표시되는 *최종 코드*의 실행 결과를 생성합니다.
        # 기존 서비스는 AST가 동일한 서식 변경만 발생하면 검증을 생략합니다.
        # 원본과 최종 코드를 비교해야 실행 결과 두 칸을 표시할 수 있습니다.
        if formatting_profile is not None and transformed_code != code_before_format:
            try:
                final_check = verify_execution_equivalence(
                    original_code=request.code,
                    transformed_code=transformed_code,
                    function_cases=function_cases,
                )
            except Exception as error:
                final_check = None
                warnings.append(
                    "서식 적용 후 실행 검증기에 오류가 발생했습니다: "
                    + type(error).__name__
                )

            check_valid = isinstance(final_check, dict)
            if check_valid:
                check_status = final_check.get("status")
                equivalent = final_check.get("equivalent")
                check_valid = (
                    check_status in ("equivalent", "different", "not_verified")
                    and type(equivalent) in (bool, type(None))
                    and (check_status != "equivalent" or equivalent is True)
                    and (check_status != "different" or equivalent is False)
                    and (check_status != "not_verified" or equivalent is None)
                    and isinstance(final_check.get("original"), dict)
                    and isinstance(final_check.get("transformed"), dict)
                )

            if not check_valid:
                # Missing/contradictory verification must not silently count
                # as a successful formatting action.  Keep verified tag edits.
                transformed_code = code_before_format
                del applied_rules[rules_before_format:]
                summary = summary_before_format + (
                    " 서식 변경의 실행 검증 결과가 불완전하여 서식만 취소했습니다."
                )
                warnings.append(
                    "서식 적용 후 실행 결과를 검증하지 못해 서식 변경을 취소했습니다."
                )
            elif final_check["status"] == "different":
                # Preserve earlier tag transforms if they had passed their own
                # checks.  Only the newly applied formatting is rolled back.
                transformed_code = code_before_format
                del applied_rules[rules_before_format:]
                summary = summary_before_format + (
                    " 서식 변환 후 실행 결과가 달라 서식 변경을 취소했습니다."
                )
                warnings.append(
                    "서식 적용 전후 실행 결과가 달라 서식 변경을 취소했습니다. "
                    "문법/개념 태그 변환 결과는 기존 검증 판정을 유지합니다."
                )
                if execution_verification is None:
                    # Display why formatting was rejected.  This report is for
                    # the *attempted* formatting, not a successfully changed code.
                    execution_verification = final_check
            else:
                # Recheck the actual displayed result, including optional
                # function cases; pre-format verification would be stale.
                execution_verification = final_check
                summary = summary.replace(
                    "문법/개념 태그 변환으로 인한 구조 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                    "최종 서식 적용 후 원본 코드와 실행 결과를 비교했습니다.",
                ).replace(
                    "최종 코드 변경이 없어 별도의 실행 결과 비교를 수행하지 않았습니다.",
                    "최종 서식 적용 후 원본 코드와 실행 결과를 비교했습니다.",
                )
                if final_check["status"] == "not_verified":
                    warnings.append(
                        "최종 서식 적용 후 실행 동등성을 확인하지 못했습니다. "
                        "화면의 검증 메시지를 확인해 주세요."
                    )

'''
    source = source.replace(return_anchor, after_format + return_anchor, 1)
    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise InstallationError("수정 후 스타일 적용 라우트 문법 검사에 실패했습니다.") from exc
    return source


def _decode(source: bytes) -> tuple[str, bool, bool]:
    bom = source.startswith(b"\xef\xbb\xbf")
    raw = source[3:] if bom else source
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallationError("스타일 적용 라우트가 UTF-8이 아닙니다. 변경하지 않습니다.") from exc
    crlf = b"\r\n" in raw
    return text.replace("\r\n", "\n"), bom, crlf


def plan(root: Path) -> tuple[Path, bytes, bytes] | None:
    target = Path(root) / "backend/app/api/routes/style_apply.py"
    if not target.is_file():
        raise InstallationError("스타일 적용 라우트를 찾지 못했습니다: " + str(target))
    old = target.read_bytes()
    content, bom, crlf = _decode(old)
    new = patch_route(content)
    if new == content:
        return None
    if crlf:
        new = new.replace("\n", "\r\n")
    encoded = (b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8")
    return target, old, encoded


def install(root: Path, backup_root: Path | None = None) -> str:
    change = plan(root)
    if change is None:
        return "이미 서식 실행 결과 복구 기능이 설치되어 있습니다."
    target, old, new = change
    root = Path(root)
    if backup_root is None:
        git = root / ".git"
        backup_root = git / "capstone_formatting_execution_fix_backup" if git.is_dir() else Path(tempfile.mkdtemp(prefix="capstone_format_exec_backup_"))
    backup = Path(backup_root) / target.relative_to(root)
    if backup.exists():
        raise InstallationError("기존 백업을 덮어쓰지 않습니다: " + str(backup))
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(old)
    try:
        target.write_bytes(new)
    except BaseException:
        target.write_bytes(old)
        raise
    return "수정 완료: " + str(target.relative_to(root)) + "\n백업: " + str(backup)


def main() -> int:
    args = sys.argv[1:]
    if args not in ([], ["--check"]):
        print("사용법: python backend/tools/install_formatting_execution_fix.py [--check]")
        return 2
    root = Path(__file__).resolve().parents[2]
    try:
        if args:
            planned = plan(root)
            print("[사전 검사] 패치 가능, 실제 파일 변경 없음" if planned is not None else "[사전 검사] 이미 설치됨")
        else:
            print("[완료] " + install(root))
    except (InstallationError, OSError) as exc:
        print("[설치 중단] " + str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
