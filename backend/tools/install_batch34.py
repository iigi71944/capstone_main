"""Windows-safe additive installer: 34차 스타일 적용 경로와 엄격 검증 감사.

capstone_main 루트에서 실행:
    python backend/tools/install_batch34.py --check
    python backend/tools/install_batch34.py

이미 존재하는 백엔드, 프론트엔드 파일은 변경하지 않습니다.
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
PAYLOAD_DIR = Path(__file__).resolve().parent / "batch34_payload"
PAYLOADS = {
    "audit_transform_batch34.py.source": ROOT / "backend/tools/audit_transform_batch34.py",
    "test_style_batch34_real_plan_runtime.py.source": ROOT / "backend/tests/test_style_batch34_real_plan_runtime.py",
}
SHA256 = {
    "audit_transform_batch34.py.source": "ec6b7b73ffeb61fa8a87990c8eae439395b8f0db3add6dfdabbbf8e91a0d7565",
    "test_style_batch34_real_plan_runtime.py.source": "494a35ec916bc6b14d67ee72f1cfc2b9bd5b719b026f12255b0432a2c76fb2f7",
}
PREVIOUS_AUDIT_SHA256 = "350cc70eec9442dc32fb364ba279298bc498b1d5da56684b59c1d4e4c6c7261b"
EXPECTED = {
    "딕셔너리 컴프리헨션": "create_dict_comprehension",
    "리스트 누적 방식 사용": "create_append_collection",
    "리스트 컴프리헨션": "create_comprehension_collection",
    "인덱스 기반 반복 사용": "create_index_iteration",
    "인덱싱 중심 구조": "create_index_iteration",
    "직접 반복 사용": "create_direct_iteration",
}
REQUIRED_SELECTED_ACTIONS = {
    "create_safe_dict_comprehension",
    "create_safe_append_collection",
    "create_safe_comprehension_collection",
    "create_index_iteration",
    "create_direct_iteration",
}


class InstallationError(Exception):
    pass


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_python(path: Path) -> ast.AST:
    try:
        return ast.parse(path.read_bytes().decode("utf-8-sig"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise InstallationError(f"기준 파일 확인 실패: {path}: {exc}") from exc


def _registry(tree: ast.AST) -> dict[str, str]:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "CREATE_ACTION_BY_TAG" and isinstance(node.value, ast.Dict):
                try:
                    return ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError):
                    break
    raise InstallationError("태그 목록의 등록 형식을 확인하지 못했습니다.")


def _static_dispatch(tree: ast.AST) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_get_transform_function":
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Dict)
                        and any(isinstance(x, ast.Name) and x.id == "action_map" for x in sub.targets)):
                    return {x.value for x in sub.value.keys
                            if isinstance(x, ast.Constant) and isinstance(x.value, str)}
    raise InstallationError("변환기 연결표(action_map)를 확인할 수 없습니다.")


def preflight():
    if not (ROOT / ".git").exists() or not (ROOT / "docker-compose.yml").is_file():
        raise InstallationError("capstone_main Git 프로젝트 루트에서 실행해 주세요.")
    registry = _registry(_read_python(ROOT / "backend/app/services/style_tag_transform_map_service.py"))
    if len(registry) != 102 or any(registry.get(tag) != expected for tag, expected in EXPECTED.items()):
        raise InstallationError("31차의 102태그 공개 액션 등록 상태가 다릅니다.")
    dispatcher = _static_dispatch(_read_python(ROOT / "backend/app/services/style_apply_service.py"))
    if not REQUIRED_SELECTED_ACTIONS.issubset(dispatcher):
        raise InstallationError("안전형·반복문 액션 등록이 확인되지 않습니다.")
    plan_path = ROOT / "backend/app/services/style_transform_plan_service.py"
    plan_tree = _read_python(plan_path)
    try:
        plan_text = plan_path.read_bytes().decode("utf-8-sig")
    except (UnicodeError, OSError) as exc:
        raise InstallationError(f"스타일 계획 파일을 읽지 못했습니다: {exc}") from exc
    # 34차의 주제인 기존 계획 선택 논리가 남아있는지 사전 보호.
    for name in ("create_safe_dict_comprehension", "create_safe_append_collection", "create_safe_comprehension_collection"):
        if name not in plan_text:
            raise InstallationError(f"계획의 안전형 액션이 없습니다: {name}")

    old_audit = ROOT / "backend/tools/audit_transform_batch33.py"
    _read_python(old_audit)
    try:
        digest = _digest(old_audit.read_bytes())
    except OSError as exc:
        raise InstallationError(f"33차 감사 도구 확인 불가: {exc}") from exc
    if digest != PREVIOUS_AUDIT_SHA256:
        raise InstallationError("33차 감사 파일의 버전이 다릅니다. 파일을 변경하지 않고 중단합니다.")
    _read_python(ROOT / "backend/tools/audit_transform_batch32.py")

    changes = []
    for filename, dest in PAYLOADS.items():
        path = PAYLOAD_DIR / filename
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise InstallationError(f"설치 구성요소가 없습니다: {filename}") from exc
        if _digest(raw) != SHA256[filename]:
            raise InstallationError(f"SHA-256 검증 실패: {filename}")
        try:
            ast.parse(raw.decode("utf-8-sig"), filename=str(dest))
        except (UnicodeError, SyntaxError) as exc:
            raise InstallationError(f"추가 파일 문법 오류: {filename}: {exc}") from exc
        if dest.is_symlink():
            raise InstallationError(f"심볼릭 링크는 수정하지 않습니다: {dest}")
        existing = dest.exists()
        if existing:
            try:
                current = dest.read_bytes()
            except OSError as exc:
                raise InstallationError(f"기존 파일 확인 불가: {dest}: {exc}") from exc
            if current != raw:
                raise InstallationError(f"동일한 파일이 이미 존재하여 덮어쓰지 않습니다: {dest}")
        changes.append((dest, raw, existing))
    return changes


def install(changes):
    created = []
    temps = []
    try:
        for destination, payload, exists in changes:
            if exists:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".batch34_", suffix=".tmp", dir=str(destination.parent))
            tmp = Path(tmp_name)
            temps.append(tmp)
            with os.fdopen(fd, "wb") as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            if destination.exists() or destination.is_symlink():
                raise InstallationError(f"설치 중 다른 파일이 생성됐습니다: {destination}")
            os.replace(tmp, destination)
            temps.remove(tmp)
            created.append(destination)
    except Exception:
        for destination in reversed(created):
            try:
                destination.unlink()
            except OSError:
                pass
        raise
    finally:
        for tmp in temps:
            try:
                tmp.unlink()
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="수정 없이 설치 전 검사만 실행")
    args = parser.parse_args()
    try:
        changes = preflight()
        for path, _, exists in changes:
            print(("이미 설치됨: " if exists else "설치 예정: ") + str(path.relative_to(ROOT)))
        if args.check:
            print("34차 --check OK: 기존 소스·프론트엔드·이전 테스트 수정 없음")
        else:
            install(changes)
            print("34차 설치 완료: 감사 도구 1개 + 회귀 테스트 18건")
    except (InstallationError, OSError) as exc:
        print(f"34차 설치 중단 (기존 파일 유지): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
