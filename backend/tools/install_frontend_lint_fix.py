#!/usr/bin/env python3
"""35차 소규모 프론트엔드 ESLint 오류/경고 수정.

기존 저장/공유 로직과 JSX/CSS/UI를 변경하지 않습니다.
Windows PowerShell: python backend\\tools\\install_frontend_lint_fix.py --check
                    python backend\\tools\\install_frontend_lint_fix.py
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = Path('frontend/hooks/useCodingStyles.ts')
APPLY = Path('frontend/components/sections/StyleApplySection.tsx')
TEST = Path('frontend/tests/duplicate-style-name.test.mjs')
BACKUP = ROOT / '.git' / 'capstone_frontend_lint_fix_backup_20261117'
MARKER = 'CAPSTONE_FRONTEND_LINT_EFFECT_SCHEDULE_V1'
DUPLICATE_MARKER = 'CAPSTONE_STYLE_NAME_DUPLICATE_SAVE_V1'

ORIGINAL_EFFECT = '''  useEffect(() => {
    const rawUser = localStorage.getItem(CURRENT_USER_STORAGE_KEY);
    if (!rawUser) {
      loadStylesByEmail(GUEST_EMAIL);
      return;
    }

    try {
      const parsedUser = JSON.parse(rawUser) as AuthUser;
      setCurrentUser(parsedUser);
      loadStylesByEmail(parsedUser.email);
    } catch {
      localStorage.removeItem(CURRENT_USER_STORAGE_KEY);
      loadStylesByEmail(GUEST_EMAIL);
    }
  }, []);'''

REVISED_EFFECT = '''  useEffect(() => {
    // CAPSTONE_FRONTEND_LINT_EFFECT_SCHEDULE_V1: localStorage 복원은 effect 뒤의 작업으로 예약합니다.
    // 언마운트 시 예약을 취소하므로 React 개발 모드의 effect 재실행도 안전합니다.
    const timerId = window.setTimeout(() => {
      const rawUser = localStorage.getItem(CURRENT_USER_STORAGE_KEY);
      if (!rawUser) {
        loadStylesByEmail(GUEST_EMAIL);
        return;
      }

      try {
        const parsedUser = JSON.parse(rawUser) as AuthUser;
        setCurrentUser(parsedUser);
        loadStylesByEmail(parsedUser.email);
      } catch {
        localStorage.removeItem(CURRENT_USER_STORAGE_KEY);
        loadStylesByEmail(GUEST_EMAIL);
      }
    }, 0);

    return () => window.clearTimeout(timerId);
  }, []);'''

UNUSED_STATUS_LABEL = '''function getStatusLabel(
  status: VerificationStatus
): string {
  if (status === "equivalent") {
    return "일치";
  }

  if (status === "different") {
    return "불일치";
  }

  return "검증 불가";
}

'''

UNUSED_TEST_DESTRUCTURE = '''const {
  DUPLICATE_STYLE_NAME_MESSAGE,
  isDuplicateCodingStyleName,
} = policy.exports;'''
FIXED_TEST_DESTRUCTURE = '''const { DUPLICATE_STYLE_NAME_MESSAGE } = policy.exports;'''


def _read(path: Path) -> tuple[str, bytes, str, bytes]:
    raw = path.read_bytes()
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    content = raw[len(bom):].decode('utf-8')
    if '\r' in content.replace('\r\n', ''):
        raise ValueError(f'{path.relative_to(ROOT)}: 알 수 없는 줄바꿈이 있습니다.')
    eol = '\r\n' if '\r\n' in content else '\n'
    return content.replace('\r\n', '\n'), bom, eol, raw


def _replace_exactly_once(source: str, before: str, after: str, description: str) -> str:
    count = source.count(before)
    if count != 1:
        raise ValueError(f'{description}: 예상한 코드가 정확히 1회 있어야 합니다. 현재 {count}회')
    return source.replace(before, after, 1)


def _new_bytes(text: str, bom: bytes, eol: str) -> bytes:
    return bom + text.replace('\n', eol).encode('utf-8')


def _prepare() -> tuple[dict[Path, bytes], dict[Path, bytes], bool]:
    originals: dict[Path, bytes] = {}
    updated: dict[Path, bytes] = {}
    for rel in (HOOK, APPLY, TEST):
        absolute = ROOT / rel
        if not absolute.is_file():
            raise ValueError(f'{rel}: 파일을 찾지 못했습니다.')
        text, bom, eol, raw = _read(absolute)
        originals[rel] = raw

        if rel == HOOK:
            if DUPLICATE_MARKER not in text:
                raise ValueError('중복 이름 저장 방지 패치가 설치되지 않았습니다.')
            if MARKER in text:
                updated[rel] = raw
                continue
            new_text = _replace_exactly_once(text, ORIGINAL_EFFECT, REVISED_EFFECT,
                                             'useCodingStyles 초기 localStorage 복원')
        elif rel == APPLY:
            if UNUSED_STATUS_LABEL not in text:
                updated[rel] = raw
                continue
            new_text = _replace_exactly_once(text, UNUSED_STATUS_LABEL, '',
                                             'StyleApplySection 미사용 함수')
        else:
            if UNUSED_TEST_DESTRUCTURE not in text:
                updated[rel] = raw
                continue
            new_text = _replace_exactly_once(text, UNUSED_TEST_DESTRUCTURE,
                                             FIXED_TEST_DESTRUCTURE, '중복 이름 테스트 미사용 변수')
        updated[rel] = _new_bytes(new_text, bom, eol)

    already = MARKER in originals[HOOK].decode('utf-8-sig')
    if already:
        if updated != originals:
            raise ValueError('일부만 설치된 상태입니다. 자동 덮어쓰기를 중단합니다.')
        if ORIGINAL_EFFECT in originals[HOOK].decode('utf-8-sig'):
            raise ValueError('패치 표식과 이전 effect 코드가 함께 존재합니다.')
    return originals, updated, already


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.capstone_lint_')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        old, new, already = _prepare()
        if already:
            print('프론트엔드 ESLint 수정이 이미 적용되어 있습니다. 재설치하지 않습니다.')
            return 0
        if args.check:
            print('사전 검사 통과: 저장 훅, 스타일 적용 화면, 중복 이름 테스트의 정확한 코드 위치 확인.')
            for p in new:
                print(('수정 예정' if new[p] != old[p] else '변경 없음') + ': ' + str(p))
            return 0
        if not (ROOT / '.git').exists():
            raise ValueError('프로젝트 .git 폴더가 없습니다. 원본 백업을 위해 Git 저장소에서 실행해주세요.')
        for rel in old:
            if (BACKUP / rel).exists():
                raise ValueError(f'백업 파일이 이미 존재합니다: {BACKUP / rel}')
        for rel, data in old.items():
            _write(BACKUP / rel, data)
        touched = []
        try:
            for rel, data in new.items():
                if data != old[rel]:
                    _write(ROOT / rel, data)
                    touched.append(rel)
        except BaseException:
            for rel in touched:
                _write(ROOT / rel, old[rel])
            raise
        print('프론트엔드 ESLint 수정 설치 완료.')
        for rel in new:
            if old[rel] != new[rel]:
                print('수정: ' + str(rel))
        print('원본 백업: .git/capstone_frontend_lint_fix_backup_20261117/')
        print('설치 후 docker compose run --rm frontend npm run lint 을 실행해주세요.')
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print('설치 중단 (원본 보존): ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
