#!/usr/bin/env python3
"""Install the exact-name duplicate guard for saved coding styles.

Run from the capstone_main project root:
  python backend/tools/install_style_name_duplicate.py --check
  python backend/tools/install_style_name_duplicate.py

Safe for Windows UTF-8 BOM and CRLF; never edits design/layout components.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_ROOT = Path(__file__).with_name('style_name_duplicate_payload')
TARGET_HOOK = ROOT / 'frontend/hooks/useCodingStyles.ts'
TARGET_POLICY = ROOT / 'frontend/lib/codingStyleNameValidation.ts'
TARGET_TEST = ROOT / 'frontend/tests/duplicate-style-name.test.mjs'
BACKUP_ROOT = ROOT / '.git/capstone_style_name_duplicate_backup_20261117'
MARKER = 'CAPSTONE_STYLE_NAME_DUPLICATE_SAVE_V1'

IMPORT_ANCHOR = 'import { createCodingStyleId } from "../lib/codingStyleFactory";'
IMPORT_EXTRA = (
    'import {\n'
    '  DUPLICATE_STYLE_NAME_MESSAGE,\n'
    '  isDuplicateCodingStyleName,\n'
    '} from "../lib/codingStyleNameValidation";'
)
SAVE_ANCHOR = '''  const saveCodingStyle = (style: SharedCodingStyle): boolean => {
    const saved = saveStylesToStorage([style, ...savedStyles]);
    if (saved) alert("코딩 스타일이 저장되었습니다.");
    return saved;
  };'''
SAVE_REPLACEMENT = '''  // CAPSTONE_STYLE_NAME_DUPLICATE_SAVE_V1: 이름 중복은 저장 직전에 검사합니다.
  const saveCodingStyle = (style: SharedCodingStyle): boolean => {
    // 기본 이름은 스타일 생성 시 이미 확정됩니다. 앞뒤 공백을 제거해 저장합니다.
    const name = style.name.trim();
    const storageKey = getStyleStorageKey(currentUser?.email || GUEST_EMAIL);
    let currentStyles: SharedCodingStyle[] = [];

    // 다른 탭에서 방금 저장한 이름도 차단하도록 저장소를 재조회합니다.
    // 데이터가 손상되었다면 기존 목록을 빈 배열로 덮어쓰지 않습니다.
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw !== null) {
        const parsed: unknown = JSON.parse(raw);
        if (
          !Array.isArray(parsed) ||
          !parsed.every(
            (item) =>
              item &&
              typeof item === "object" &&
              typeof (item as { name?: unknown }).name === "string"
          )
        ) {
          alert("저장된 코딩 스타일 정보를 읽을 수 없어 저장을 중단했습니다.");
          return false;
        }
        currentStyles = parsed as SharedCodingStyle[];
      }
    } catch (error) {
      console.error("코딩 스타일 목록 조회 오류:", error);
      alert("저장된 코딩 스타일 정보를 읽을 수 없어 저장을 중단했습니다.");
      return false;
    }

    if (isDuplicateCodingStyleName(name, currentStyles)) {
      alert(DUPLICATE_STYLE_NAME_MESSAGE);
      return false;
    }

    const saved = saveStylesToStorage([{ ...style, name }, ...currentStyles]);
    if (saved) alert("코딩 스타일이 저장되었습니다.");
    return saved;
  };'''

# SHA-256 values are embedded when the final release is packed.
PAYLOAD_SHA256 = {
    'codingStyleNameValidation.ts.source': '4aa04252c8f527833e88209bc8ee72d0a93e8d886a7f4cd7d2000a85b1f49b9a',
    'duplicate-style-name.test.mjs.source': '36195cdb9fd5cc95c6b8326c88c4cc640c173b14de0bbbb2848c62e6d1fa1496',
}


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _decode_source(raw: bytes) -> tuple[str, bytes, str]:
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    source = raw[len(bom):].decode('utf-8')
    if '\r' in source.replace('\r\n', ''):
        raise ValueError('CRLF/LF 외 줄바꿈이 있습니다.')
    eol = '\r\n' if '\r\n' in source else '\n'
    return source.replace('\r\n', '\n'), bom, eol


def _exactly_once(source: str, anchor: str, description: str) -> None:
    count = source.count(anchor)
    if count != 1:
        raise ValueError(f'{description}: 예상한 기준 코드가 정확히 1회여야 합니다. 발견: {count}')


def _preflight():
    if not TARGET_HOOK.is_file():
        raise ValueError('frontend/hooks/useCodingStyles.ts 파일을 찾지 못했습니다. 프로젝트 루트 확인이 필요합니다.')
    raw = TARGET_HOOK.read_bytes()
    text, bom, eol = _decode_source(raw)
    has_marker = MARKER in text
    extras_exist = (TARGET_POLICY.exists(), TARGET_TEST.exists())
    if has_marker and all(extras_exist):
        for name, target in (
            ('codingStyleNameValidation.ts.source', TARGET_POLICY),
            ('duplicate-style-name.test.mjs.source', TARGET_TEST),
        ):
            expected = PAYLOAD_ROOT.joinpath(name).read_bytes()
            if _sha(expected) != PAYLOAD_SHA256[name] or target.read_bytes() != expected:
                raise ValueError(f'설치 흔적이 있으나 {target.name}이(가) 기준 버전과 다릅니다. 수동 확인이 필요합니다.')
        return {'already': True}
    if has_marker or any(extras_exist):
        raise ValueError('일부 파일이 이미 존재합니다. 다른 변경을 덮어쓰지 않도록 설치를 중단합니다.')

    _exactly_once(text, IMPORT_ANCHOR, '기존 코드의 import 위치')
    _exactly_once(text, SAVE_ANCHOR, '코딩 스타일 저장 함수')
    new_text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + '\n' + IMPORT_EXTRA)
    new_text = new_text.replace(SAVE_ANCHOR, SAVE_REPLACEMENT)
    assert MARKER in new_text
    new_raw = bom + new_text.replace('\n', eol).encode('utf-8')

    payloads = []
    for name, target in (
        ('codingStyleNameValidation.ts.source', TARGET_POLICY),
        ('duplicate-style-name.test.mjs.source', TARGET_TEST),
    ):
        content = PAYLOAD_ROOT.joinpath(name).read_bytes()
        if _sha(content) != PAYLOAD_SHA256[name]:
            raise ValueError(f'페이로드 SHA-256 무결성 검사 실패: {name}')
        payloads.append((target, content))
    return {'already': False, 'original': raw, 'updated': new_raw, 'payloads': payloads}


def _atomic_write(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix='.capstone_name_guard_', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='파일은 수정하지 않고 사전 검사만 합니다.')
    args = parser.parse_args()
    try:
        plan = _preflight()
        if plan['already']:
            print('중복 이름 방지 패치가 이미 설치되어 있습니다. 재설치하지 않습니다.')
            return 0
        if args.check:
            print('중복 이름 방지 패치 사전 검사 통과: 기존 저장 훅 1개, 신규 파일 2개, SHA-256 정상.')
            print('변경 예정: frontend/hooks/useCodingStyles.ts (화면 구성 변경 없음)')
            return 0

        if not (ROOT / '.git').exists():
            raise ValueError('Git 저장소(.git)를 찾지 못했습니다. 백업 위치를 보장할 수 없습니다.')
        backup = BACKUP_ROOT / 'frontend/hooks/useCodingStyles.ts'
        if backup.exists():
            raise ValueError('동일 이름의 원본 백업이 이미 존재해 덮어쓰지 않습니다.')
        _atomic_write(backup, plan['original'])
        created = []
        try:
            _atomic_write(TARGET_HOOK, plan['updated'])
            for dest, blob in plan['payloads']:
                _atomic_write(dest, blob)
                created.append(dest)
        except Exception:
            _atomic_write(TARGET_HOOK, plan['original'])
            for dest in created:
                dest.unlink(missing_ok=True)
            raise

        print('중복 코딩 스타일 이름 저장 방지 패치 설치 완료.')
        print('변경: frontend/hooks/useCodingStyles.ts')
        print('추가: frontend/lib/codingStyleNameValidation.ts')
        print('추가: frontend/tests/duplicate-style-name.test.mjs')
        print(f'원본 백업: {backup.relative_to(ROOT)}')
        print('중복 시 팝업: 저장하려는 코딩 스타일 이름이 중복됩니다. 다른 이름을 작성해주세요')
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f'중복 이름 방지 패치 설치 중단 (기존 파일 보존): {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
