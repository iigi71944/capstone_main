"""기존 사용자 분석 파일을 보존하면서 주석 제외 분석을 연결하는 설치기.

실행 위치와 무관하게 backend/app/api/routes/analyze.py 및
backend/app/services/style_diff_service.py의 parse_code() 호출을
분석 전용 AST 필터로 감싼다. 다른 모듈이나 프론트엔드는 수정하지 않는다.
"""

from __future__ import annotations

import ast
import datetime
import os
import shutil
import sys
import tempfile
from pathlib import Path

IMPORT_LINE = (
    "from app.services.style_analysis_comment_filter_service "
    "import without_analysis_comments"
)
TARGETS = (
    "app/api/routes/analyze.py",
    "app/services/style_diff_service.py",
)


class InstallationError(RuntimeError):
    pass


def _offset(lines: list[bytes], lineno: int, column: int) -> int:
    return sum(len(line) for line in lines[:lineno - 1]) + column


def _import_insertion_line(tree: ast.Module) -> int:
    """모듈 독스트링과 future import 이후, 실제 코드 앞에 삽입한다."""
    body = tree.body
    cursor = 0
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        cursor = 1
    while (
        cursor < len(body)
        and isinstance(body[cursor], ast.ImportFrom)
        and body[cursor].module == "__future__"
    ):
        cursor += 1
    if cursor == 0:
        return 1
    return body[cursor - 1].end_lineno + 1


def patched_source(source: str, filename: str = "<source>") -> tuple[str, bool]:
    """지원하는 소스에만 최소 변경 적용. 아니면 명확하게 실패한다."""
    original = source.encode("utf-8")
    source_ast = ast.parse(source, filename=filename)
    if IMPORT_LINE in source:
        return source, False

    selected: list[ast.Call] = []
    for node in ast.walk(source_ast):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if (
            (isinstance(callee, ast.Name) and callee.id == "parse_code")
            or (
                isinstance(callee, ast.Attribute)
                and callee.attr == "parse_code"
            )
        ):
            selected.append(node)

    if not selected:
        raise InstallationError(
            f"{filename}: parse_code() 호출을 찾지 못했습니다. "
            "안전을 위해 자동 수정하지 않습니다. 원본 파일을 확인해 주세요."
        )

    lines = original.splitlines(keepends=True)
    changes: list[tuple[int, bytes]] = []
    for call in selected:
        start = _offset(lines, call.lineno, call.col_offset)
        end = _offset(lines, call.end_lineno, call.end_col_offset)
        # 기존 parse_code(...) 호출을 괄호로 감싸며 코드 내용은 그대로 보존.
        changes.append((end, b")"))
        changes.append((start, b"without_analysis_comments("))

    # 먼저 원문의 상대적 위치를 유지하면서 역순으로 치환.
    patched = original
    for pos, data in sorted(changes, reverse=True):
        patched = patched[:pos] + data + patched[pos:]

    # AST 원문에서 얻은 줄 번호를 사용하되, 삽입한 괄호에 따른 줄 수는 변하지 않는다.
    patched_lines = patched.splitlines(keepends=True)
    insert_line = _import_insertion_line(source_ast)
    patched_lines.insert(insert_line - 1, (IMPORT_LINE + "\n").encode("utf-8"))
    result = b"".join(patched_lines).decode("utf-8")
    ast.parse(result, filename=filename)
    return result, True


def install(backend_root: Path, backup_root: Path | None = None) -> dict[str, str]:
    """모든 파일을 먼저 검사하고 성공한 경우에만 수정한다."""
    backend_root = Path(backend_root)
    proposed: list[tuple[Path, str, str]] = []
    report: dict[str, str] = {}

    for rel in TARGETS:
        target = backend_root / rel
        if not target.is_file():
            raise InstallationError(f"필수 파일을 찾지 못했습니다: {target}")
        old = target.read_text(encoding="utf-8-sig")
        new, changed = patched_source(old, str(target))
        report[rel] = "수정" if changed else "이미 적용됨"
        if changed:
            proposed.append((target, old, new))

    if not proposed:
        return report

    if backup_root is None:
        project_root = backend_root.parent
        git_dir = project_root / ".git"
        if git_dir.is_dir():
            backup_root = git_dir / "capstone_comment_filter_backup"
        else:
            backup_root = Path(tempfile.mkdtemp(prefix="capstone_comment_filter_backup_"))
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)

    # 현재 Git 프로젝트가 없는 경우에도 원본 소스 백업을 남긴다.
    for target, original, _ in proposed:
        rel = target.relative_to(backend_root)
        dest = backup_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(original, encoding="utf-8")

    try:
        for target, _, updated in proposed:
            target.write_text(updated, encoding="utf-8")
    except Exception:
        # 도중 실패 시 손상 없는 상태로 복원
        for target, original, _ in proposed:
            target.write_text(original, encoding="utf-8")
        raise

    report["backup"] = str(backup_root)
    return report


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    try:
        outcome = install(backend_root)
    except (InstallationError, OSError, SyntaxError, UnicodeError) as exc:
        print(f"[설치 중단] {exc}", file=sys.stderr)
        return 1

    print("=== 스타일 분석 주석 제외 기능 연결 ===")
    for key, value in outcome.items():
        print(f"{key}: {value}")
    print("원본 코드는 유지하며 분석용 AST에만 필터를 적용합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
