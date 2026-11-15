#!/usr/bin/env python3
"""Install one source-viewer UI patch without touching style logic or saved data.

Usage from repository root:
  python tools/install_codeviewer_autoheight.py --check
  python tools/install_codeviewer_autoheight.py

Checks the exact GitHub CodeViewer.tsx baseline from commit e9f4b6b,
with LF/CRLF and optional UTF-8 BOM tolerance. Never overwrites local edits.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/components/editor/CodeViewer.tsx"
PAYLOAD = ROOT / "tools/codeviewer_payload/CodeViewer.tsx.source"
BACKUP = ROOT / ".git/capstone_codeviewer_backups/CodeViewer.tsx.before_autoheight"
BASE_BLOB_SHA = "360565591c062c618e5dbdfc54702fc7128a03ff"
MARKER = "CAPSTONE_CODE_VIEWER_AUTOHEIGHT_V1"


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _decode_normalized(data: bytes) -> tuple[str, str, bool]:
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    if "\r\n" in text:
        eol = "\r\n"
    else:
        eol = "\n"
    return text.replace("\r\n", "\n"), eol, bom


def _out_bytes(text: str, eol: str, bom: bool) -> bytes:
    raw = text.replace("\n", eol).encode("utf-8")
    return (b"\xef\xbb\xbf" if bom else b"") + raw


def install(*, check: bool) -> str:
    if not TARGET.is_file():
        raise RuntimeError("frontend/components/editor/CodeViewer.tsx 파일을 찾지 못했습니다.")
    if not PAYLOAD.is_file():
        raise RuntimeError("ZIP의 CodeViewer.tsx.source 파일이 없습니다. 다시 압축 해제해 주세요.")
    if not (ROOT / "frontend" / "package.json").is_file():
        raise RuntimeError("capstone_main 프로젝트 최상위 폴더에서 실행해 주세요.")

    old = TARGET.read_bytes()
    old_text, eol, bom = _decode_normalized(old)
    payload_text, _, _ = _decode_normalized(PAYLOAD.read_bytes())
    if MARKER not in payload_text:
        raise RuntimeError("설치용 소스 파일의 식별자가 누락되었습니다.")

    if MARKER in old_text:
        if old_text != payload_text:
            raise RuntimeError("15차 이후의 CodeViewer 변경이 감지되었습니다. 덮어쓰지 않습니다.")
        return "이미 적용되어 있습니다. 추가 변경은 없습니다."

    # Compare exact source content; tolerate Windows CRLF and editor-added EOF newline.
    candidates = [old_text.encode("utf-8")]
    if old_text.endswith("\n"):
        candidates.append(old_text[:-1].encode("utf-8"))
    if not any(_blob_sha(candidate) == BASE_BLOB_SHA for candidate in candidates):
        raise RuntimeError(
            "현재 CodeViewer.tsx가 기준 커밋(e9f4b6b)과 다릅니다. "
            "기존 변경 사항을 보호하기 위해 설치를 중단합니다. "
            "내용이나 git diff를 보내주시면 맞춤 패치를 제공하겠습니다."
        )

    expected = _out_bytes(payload_text, eol, bom)
    if check:
        return (
            "설치 가능: frontend/components/editor/CodeViewer.tsx (1개 파일). "
            "기존 After 편집 기능과 실행 비교 영역은 변경하지 않습니다."
        )

    if not (ROOT / ".git").is_dir():
        raise RuntimeError(".git 폴더를 찾지 못했습니다. 백업을 남기기 위해 설치를 중단합니다.")

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if BACKUP.exists():
        if BACKUP.read_bytes() != old:
            raise RuntimeError("기존 백업이 다릅니다. 덮어쓰지 않고 중단합니다.")
    else:
        BACKUP.write_bytes(old)

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=TARGET.parent, suffix=".tmp", delete=False) as temp:
            tmp_name = temp.name
            temp.write(expected)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(tmp_name, TARGET)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)

    return (
        "적용 완료: Before/After 코드창 자동 높이 및 페이지 폭 내 자동 줄바꿈. "
        ".git/capstone_codeviewer_backups/ 경로에 원본을 백업했습니다."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="소스 변경 없이 사전 조건만 검사")
    args = parser.parse_args()
    try:
        print(install(check=args.check))
    except (OSError, UnicodeError, RuntimeError) as error:
        print("설치 중단:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
