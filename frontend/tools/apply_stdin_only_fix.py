#!/usr/bin/env python3
"""Apply the minimal, idempotent frontend stdin-only integration patch.

Usage from capstone_main root:
    python3 frontend/tools/apply_stdin_only_fix.py --check
    python3 frontend/tools/apply_stdin_only_fix.py --apply

The JSX structure/classes are preserved; only input routing and explanatory
labels change. Unrecognized existing sources fail closed.
"""
from __future__ import annotations
import argparse
from pathlib import Path

TARGET = Path('frontend/components/sections/StyleApplySection.tsx')
MARKER = 'CAPSTONE_STDIN_ONLY_INDEPENDENT_FUNCTION_CASES_V1'
START = '  const parseFunctionCases = ():\n'
END = '  const missingSyntaxNames = new Set(\n'
IMPORT_FROM = 'import FunctionReturnResults from "./FunctionReturnResults";\n'
IMPORT_TO = IMPORT_FROM + 'import { parseVerificationInputs } from "../../lib/verificationInputSelection";\n'

SUBMIT_BLOCK = '''  // CAPSTONE_STDIN_ONLY_INDEPENDENT_FUNCTION_CASES_V1:
  // An empty function name with stdin is a standalone stdin verification.
  // No function_cases are sent in this mode; the existing top-level stdin
  // reaches the execution verifier without changing backend contracts.
  const submitStyleApplication = () => {
    if (styleApplyLoading) {
      return;
    }

    if (!useFunctionTests) {
      setFunctionInputError("");
      void handleApplyStyle(undefined, false);
      return;
    }

    const selected = parseVerificationInputs(functionDrafts);
    if (!selected.ok) {
      setFunctionInputError(selected.error);
      return;
    }

    setFunctionInputError("");
    void handleApplyStyle(selected.functionCases, false, selected.stdin);
  };

'''

LABELS = (
    ('                  함수 반환값 검증\n', '                  표준 입력 및 함수 반환값 검증\n'),
    ('                  함수 검증 사용\n', '                  입력/함수 검증 사용\n'),
    ('                  함수에 같은 값을 넣어 실행한 뒤,\n                  스타일 적용 전후의 결과가 같은지\n                  확인합니다.\n',
     '                  입력값만 작성하면 실행 출력을 비교하고,\n                  함수 이름까지 입력하면 반환값도\n                  함께 검증합니다.\n'),
    ('                    코드에 작성된 함수 이름과\n                    함수에 넣을 값을 입력해주세요.\n                    값을 넣는 방식은 두 가지이며,\n                    필요한 방식만 사용하시면 됩니다.\n',
     '                    표준 입력만 검증할 때는 함수 이름을 비워 두고\n                    사용자 입력값(stdin)만 입력하세요.\n                    함수 반환값 검증 시에는 함수 이름과\n                    함수에 넣을 값을 함께 입력해주세요.\n'),
    ('                            코드에 정의된 함수 이름을\n                            그대로 입력해주세요.\n',
     '                            함수 반환값 검증 시에만 입력합니다.\n                            표준 입력만 검증할 때는 비워 두세요.\n'),
    ('                            이 함수 테스트의 사용자 입력값 (stdin) ',
     '                            사용자 입력값 (stdin) '),
)


def patch_source(source: str) -> tuple[str, str]:
    # Normalize line endings only in memory; restore original format.
    crlf = '\r\n' in source
    if crlf and source.count('\r\n') != source.count('\n'):
        raise ValueError('혼합된 줄바꿈은 자동 변경하지 않습니다.')
    text = source.replace('\r\n', '\n')
    if MARKER in text:
        if IMPORT_TO not in text or 'parseVerificationInputs(functionDrafts)' not in text:
            raise ValueError('부분 적용된 파일을 발견했습니다. 수동 확인이 필요합니다.')
        return source, 'already_applied'
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError('프론트엔드의 입력 처리 구조가 예상과 다릅니다. 변경을 중단합니다.')
    if text.count(IMPORT_FROM) != 1 or IMPORT_TO in text:
        raise ValueError('import 위치가 예상과 다릅니다. 변경을 중단합니다.')
    before, remainder = text.split(START, 1)
    removed, after = remainder.split(END, 1)
    # Ensure the old block was exactly the target code's form, not an unrelated region.
    necessary = ('const cases: FunctionTestCase[] = [];',
                 'const submitStyleApplication = () => {',
                 'void handleApplyStyle(cases, false,',
                 'const functionName =',
                 'if (!functionName) {')
    if not all(fragment in removed for fragment in necessary):
        raise ValueError('기존 함수 검증 처리 형태가 다릅니다. 변경을 중단합니다.')
    text = before + SUBMIT_BLOCK + END + after
    text = text.replace(IMPORT_FROM, IMPORT_TO, 1)
    for old, new in LABELS:
        if text.count(old) != 1:
            raise ValueError('화면 안내 문구가 예상과 다릅니다: ' + old.strip()[:55])
        text = text.replace(old, new, 1)
    if crlf:
        text = text.replace('\n', '\r\n')
    return text, 'ready'


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not TARGET.exists():
        parser.error(f'{TARGET} 파일이 없습니다. capstone_main 프로젝트 루트에서 실행해주세요.')
    try:
        original = TARGET.read_bytes()
        text = original.decode('utf-8')
        patched, status = patch_source(text)
    except (OSError, UnicodeError, ValueError) as e:
        parser.error(str(e))
    if args.check:
        print(f'stdin-only frontend check: {status}')
        return 0
    if status == 'ready':
        data = patched.encode('utf-8')
        # Atomic replacement; preserve original permissions where possible.
        temp = TARGET.with_suffix(TARGET.suffix + '.stdin_only_tmp')
        try:
            temp.write_bytes(data)
            temp.chmod(TARGET.stat().st_mode)
            temp.replace(TARGET)
        finally:
            if temp.exists():
                temp.unlink()
    print(f'stdin-only frontend patch: {"applied" if status == "ready" else status}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
