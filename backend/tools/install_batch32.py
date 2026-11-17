"""Windows-safe additive installer for Batch 32 (never edits existing code).

Run at capstone_main root:
    python backend/tools/install_batch32.py --check
    python backend/tools/install_batch32.py
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = Path(__file__).resolve().parent / "batch32_payload"
PAYLOADS = {
    "audit_transform_batch32.py.source": ROOT / "backend/tools/audit_transform_batch32.py",
    "test_style_batch32_actual_success.py.source": ROOT / "backend/tests/test_style_batch32_actual_success.py",
}
# Updated on ZIP assembly. Digest validation prevents missing or altered payloads.
SHA256 = {
    "audit_transform_batch32.py.source": "09e57895367736a7ac9d1d56c56257ae23b73b2458530056faa3d8f393a77b1c",
    "test_style_batch32_actual_success.py.source": "b424c2ff54b11acd55c5038c14e2005233645bf0c3758637b226695bbe217092",
}
REQUIRED_ACTIONS = {
    "create_safe_closed_default_parameter",
    "create_safe_closed_varargs",
    "create_safe_closed_kwargs",
    "create_safe_closed_async_definition",
    "create_safe_closed_await",
    "create_safe_closed_async_structure",
    "create_safe_closed_long_function",
}


class InstallationError(Exception):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_python(path: Path) -> ast.AST:
    try:
        # Read safely on Windows, regardless of CRLF/BOM in Git checkout.
        text = path.read_bytes().decode("utf-8-sig")
        return ast.parse(text, filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise InstallationError(f"파일 읽기/문법 검사 실패: {path}: {exc}") from exc


def _declared_actions(tree: ast.AST) -> dict:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "CREATE_ACTION_BY_TAG" and isinstance(node.value, ast.Dict):
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError) as exc:
                    raise InstallationError(f"태그 등록 상태를 확인할 수 없습니다: {exc}")
                if not isinstance(value, dict):
                    break
                return value
        if isinstance(node, ast.Assign):
            if any(isinstance(x, ast.Name) and x.id == "CREATE_ACTION_BY_TAG"
                   for x in node.targets):
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError) as exc:
                    raise InstallationError(f"태그 등록 상태를 확인할 수 없습니다: {exc}")
                if not isinstance(value, dict):
                    break
                return value
    raise InstallationError("31차 태그 등록 딕셔너리를 찾지 못했습니다.")


def _dispatcher_names(tree: ast.AST) -> set[str]:
    function = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == "_get_transform_function"), None)
    if function is None:
        raise InstallationError("실제 변환기 연결 함수를 찾지 못했습니다.")
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            if any(isinstance(x, ast.Name) and x.id == "action_map"
                   for x in node.targets):
                return {x.value for x in node.value.keys
                        if isinstance(x, ast.Constant) and isinstance(x.value, str)}
    raise InstallationError("정적 action_map 등록표를 찾지 못했습니다.")


def preflight() -> list[tuple[Path, bytes, bool]]:
    if not (ROOT / ".git").exists():
        raise InstallationError("Git 프로젝트 루트(.git)가 없습니다.")
    if not (ROOT / "docker-compose.yml").is_file():
        raise InstallationError("docker-compose.yml이 없습니다.")

    registry = _declared_actions(_read_python(ROOT / "backend/app/services/style_tag_transform_map_service.py"))
    if len(registry) != 102 or not REQUIRED_ACTIONS.issubset(set(registry.values())):
        raise InstallationError(f"31차 최종 태그 연결 상태가 아닙니다 (현재 {len(registry)}개).")
    dispatch = _dispatcher_names(_read_python(ROOT / "backend/app/services/style_apply_service.py"))
    if not REQUIRED_ACTIONS.issubset(dispatch):
        raise InstallationError("31차 액션 등록 핫픽스가 누락됐습니다.")
    _read_python(ROOT / "backend/tools/audit_transform_batch31.py")

    pending: list[tuple[Path, bytes, bool]] = []
    for source_name, dest in PAYLOADS.items():
        payload_path = SOURCE_DIR / source_name
        try:
            data = payload_path.read_bytes()
        except OSError as exc:
            raise InstallationError(f"패치 내용이 없습니다: {source_name}") from exc
        if _sha(data) != SHA256[source_name]:
            raise InstallationError(f"패치 무결성 검사가 실패했습니다: {source_name}")
        try:
            ast.parse(data.decode("utf-8-sig"), filename=str(dest))
        except (SyntaxError, UnicodeError) as exc:
            raise InstallationError(f"패치 파일 문법 오류: {dest}: {exc}") from exc
        if dest.is_symlink():
            raise InstallationError(f"심볼릭 링크는 수정하지 않습니다: {dest}")
        already_installed = dest.exists()
        if already_installed:
            try:
                existing = dest.read_bytes()
            except OSError as exc:
                raise InstallationError(f"기존 파일 확인 불가: {dest}") from exc
            if existing != data:
                raise InstallationError(f"동일한 파일명이 이미 존재합니다 (덮어쓰기 거부): {dest}")
        pending.append((dest, data, already_installed))
    return pending


def install(plan: list[tuple[Path, bytes, bool]]) -> None:
    made = []
    tempfiles = []
    try:
        for target, data, already in plan:
            if already:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Create a temporary file beside the target, then an atomic replace.
            fd, tmpname = tempfile.mkstemp(prefix=".batch32_", suffix=".tmp", dir=str(target.parent))
            tmp = Path(tmpname)
            tempfiles.append(tmp)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists() or target.is_symlink():
                raise InstallationError(f"설치 중 대상 파일이 생성됐습니다: {target}")
            os.replace(tmp, target)
            tempfiles.remove(tmp)
            made.append(target)
    except Exception:
        for target in reversed(made):
            try:
                target.unlink()
            except OSError:
                pass
        raise
    finally:
        for tmp in tempfiles:
            try:
                tmp.unlink()
            except OSError:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="32차 실제 자동 변환 관측 감사 추가 (기존 코드 무수정)")
    ap.add_argument("--check", action="store_true", help="설치하지 않고 안전 조건만 검사")
    args = ap.parse_args()
    try:
        plan = preflight()
        for target, _, existing in plan:
            print(("이미 설치됨: " if existing else "설치 예정: ") + str(target.relative_to(ROOT)))
        if args.check:
            print("32차 --check OK: 원본 수정 없음, 프론트엔드 수정 없음")
        else:
            install(plan)
            print("32차 설치 완료: 감사 도구 및 회귀 테스트만 추가")
    except (InstallationError, OSError) as exc:
        print(f"32차 설치 중단 (기존 파일 유지): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
