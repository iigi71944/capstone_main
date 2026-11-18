#!/usr/bin/env python3
"""Apply batch-stdin execution result support to capstone_main (Nov 2026 main).
Run from capstone_main root: python3 frontend/tools/apply_stdin_batch_results.py --check/--apply.
Only exact expected anchors are patched. Original layout and legacy API calls remain intact.
"""
from __future__ import annotations
import argparse
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCHES: dict[str, list[tuple[str, str, int]]] = {}

def add(path: str, old: str, new: str, count: int = 1):
    PATCHES.setdefault(path, []).append((old, new, count))

SCHEMA = "backend/app/schemas/style_apply.py"
add(SCHEMA,
'''    # CAPSTONE_BATCH17_STDIN_V1: shared stdin for base execution and function cases.
    stdin: Optional[str] = Field(default=None, max_length=8192)
''',
'''    # CAPSTONE_BATCH17_STDIN_V1: shared stdin for base execution and function cases.
    stdin: Optional[str] = Field(default=None, max_length=8192)
    # CAPSTONE_BATCH37_MULTI_STDIN_V1: up to 8 independently checked stdin inputs.
    stdin_cases: Optional[List[str]] = Field(default=None, min_length=1, max_length=8)
''')
add(SCHEMA,
'''class ExecutionVerification(BaseModel):
''',
'''class StdinCaseVerification(BaseModel):
    case_number: int
    stdin: str
    status: str
    equivalent: Optional[bool] = None
    original: ExecutionResult
    transformed: ExecutionResult
    message: str


class ExecutionVerification(BaseModel):
''')
add(SCHEMA,
'''    function_verification: Optional[FunctionVerification] = None
''',
'''    function_verification: Optional[FunctionVerification] = None
    # Optional additive response field. Existing clients can ignore it.
    stdin_case_results: Optional[List[StdinCaseVerification]] = None
''')

SVC="backend/app/services/execution_validation_service.py"
add(SVC,
'''def verify_execution_equivalence(
    original_code: str,
    transformed_code: str,
    function_cases: list[dict] | None = None,
    stdin: Optional[str] = None,
) -> dict:
''',
'''def verify_execution_equivalence(
    original_code: str,
    transformed_code: str,
    function_cases: list[dict] | None = None,
    stdin: Optional[str] = None,
    stdin_cases: list[str] | None = None,
) -> dict:
''')
add(SVC,
'''    result = _verify_observed_execution(
        original_code, transformed_code,
        **({"stdin": stdin} if stdin is not None else {}),
    )

    # 기존 스타일 적용 서비스는 function_cases를 전달하지
''',
'''    # CAPSTONE_BATCH37_MULTI_STDIN_V1: compare every submitted input against
    # exactly the same before/after code. First result remains the legacy slot.
    if stdin_cases is not None:
        if (not isinstance(stdin_cases, list) or not 1 <= len(stdin_cases) <= 8
                or any(not valid_stdin_input(value) for value in stdin_cases)):
            raise ValueError("stdin_cases must contain 1 to 8 valid stdin strings")
        if stdin is not None and stdin != stdin_cases[0]:
            raise ValueError("stdin must equal the first stdin_cases entry")
        effective_stdin = stdin_cases[0]
    else:
        effective_stdin = stdin

    result = _verify_observed_execution(
        original_code, transformed_code,
        **({"stdin": effective_stdin} if effective_stdin is not None else {}),
    )

    if stdin_cases is not None:
        case_rows = []
        for index, case_stdin in enumerate(stdin_cases):
            checked = (result if index == 0 else _verify_observed_execution(
                original_code, transformed_code, stdin=case_stdin,
            ))
            case_rows.append({
                "case_number": index + 1,
                "stdin": case_stdin,
                "status": checked["status"],
                "equivalent": checked["equivalent"],
                "original": checked["original"],
                "transformed": checked["transformed"],
                "message": checked["message"],
            })
        result["stdin_case_results"] = case_rows
        outcomes = [row["status"] for row in case_rows]
        if "different" in outcomes:
            result["status"] = "different"
            result["equivalent"] = False
            result["message"] = (
                f"{len(case_rows)}개 입력 중 일부에서 변환 전후 실행 결과 차이가 발견되었습니다. "
                "전체 변환은 안전 정책에 따라 취소될 수 있습니다."
            )
        elif "not_verified" in outcomes:
            result["status"] = "not_verified"
            result["equivalent"] = None
            result["message"] = (
                f"{len(case_rows)}개 입력 중 검증하지 못한 항목이 있어 "
                "실행 동등성을 확정하지 않았습니다."
            )
        else:
            result["status"] = "equivalent"
            result["equivalent"] = True
            result["message"] = (
                f"{len(case_rows)}개 입력에서 종료 코드·표준 출력·오류가 일치했습니다. "
                "검사하지 않은 입력과 내부 상태의 동일성까지 보장하지는 않습니다."
            )

    # 기존 스타일 적용 서비스는 function_cases를 전달하지
''')
add(SVC,
'''    result["function_verification"] = None

    # 이미 차이가 확인되었다면 추가 검증이 필요하지 않습니다.
''',
'''    result["function_verification"] = None

    # Batch inputs are mandatory checks, not optional examples. A differing or
    # unverified stdin case must not be promoted to equivalent by function tests.
    if stdin_cases is not None and result["status"] != "equivalent":
        result["message"] += " 입력별 검증이 완료되지 않아 함수 테스트는 생략했습니다."
        return result

    # 이미 차이가 확인되었다면 추가 검증이 필요하지 않습니다.
''')

STYLE="backend/app/services/style_apply_service.py"
add(STYLE,
'''    strict_runtime_validation: bool = False,
    stdin: str | None = None,
):
''',
'''    strict_runtime_validation: bool = False,
    stdin: str | None = None,
    stdin_cases: list[str] | None = None,
):
''')
add(STYLE,
'''    if _is_changed(code, transformed_code) or function_cases is not None:
''',
'''    if (_is_changed(code, transformed_code) or function_cases is not None
            or stdin_cases is not None):
''')
add(STYLE,
'''                function_cases=function_cases,
                **({"stdin": stdin} if stdin is not None else {}),
''',
'''                function_cases=function_cases,
                **({"stdin": stdin} if stdin is not None else {}),
                **({"stdin_cases": stdin_cases} if stdin_cases is not None else {}),
''')

ROUTE="backend/app/api/routes/style_apply.py"
add(ROUTE,
'''        stdin_input = getattr(request, "stdin", None)
''',
'''        stdin_input = getattr(request, "stdin", None)
        # CAPSTONE_BATCH37_MULTI_STDIN_V1: optional, for old request stubs.
        stdin_cases = getattr(request, "stdin_cases", None)
''')
add(ROUTE,
'''            strict_runtime_validation=strict_runtime_validation,
            **({"stdin": stdin_input} if stdin_input is not None else {}),
''',
'''            strict_runtime_validation=strict_runtime_validation,
            **({"stdin": stdin_input} if stdin_input is not None else {}),
            **({"stdin_cases": stdin_cases} if stdin_cases is not None else {}),
''')
# Route uses same kwargs under deeper indentation for rechecks.
add(ROUTE,
'''                    **({"stdin": stdin_input} if stdin_input is not None else {}),
''',
'''                    **({"stdin": stdin_input} if stdin_input is not None else {}),
                    **({"stdin_cases": stdin_cases} if stdin_cases is not None else {}),
''', count=2)

TYPES="frontend/types/analysis.ts"
add(TYPES,
'''export type ExecutionVerification = {
''',
'''export type StdinCaseVerification = {
  case_number: number;
  stdin: string;
  status: VerificationStatus;
  equivalent: boolean | null;
  original: ExecutionResult;
  transformed: ExecutionResult;
  message: string;
};

export type ExecutionVerification = {
''')
add(TYPES,
'''  function_verification?: FunctionVerification | null;
''',
'''  function_verification?: FunctionVerification | null;
  stdin_case_results?: StdinCaseVerification[] | null;
''')
add(TYPES,
'''  stdin?: string | null;
''',
'''  stdin?: string | null;
  stdin_cases?: string[] | null;
''')
# Above matches only top-level request stdin? function case stdin has a different comment on same line.

SELECT="frontend/lib/verificationInputSelection.ts"
add(SELECT,
'''export function parseVerificationInputs(
  drafts: readonly VerificationInputDraft[]
): VerificationInputSelection {
''',
'''export function parseVerificationInputs(
  drafts: readonly VerificationInputDraft[]
): VerificationInputSelection {
  if (drafts.length > 8) return fail("입력 테스트는 최대 8개까지 생성할 수 있습니다.");
''')
add(SELECT,
'''  | { ok: true; functionCases: FunctionTestCase[] | undefined; stdin: string | undefined }
''',
'''  | { ok: true; functionCases: FunctionTestCase[] | undefined; stdin: string | undefined; stdinCases: string[] }
''')
add(SELECT,
'''  const functionCases: FunctionTestCase[] = [];
  let stdin: string | undefined;
''',
'''  const functionCases: FunctionTestCase[] = [];
  const stdinCases: string[] = [];
  let stdin: string | undefined;
''')
add(SELECT,
'''    if (stdin === undefined && rawStdin !== "") stdin = rawStdin;
''',
'''    if (rawStdin !== "") {
      stdinCases.push(rawStdin);
      if (stdin === undefined) stdin = rawStdin;
    }
''')
add(SELECT,
'''    functionCases: functionCases.length > 0 ? functionCases : undefined,
    stdin,
''',
'''    functionCases: functionCases.length > 0 ? functionCases : undefined,
    stdin,
    stdinCases,
''')

API="frontend/lib/api.ts"
add(API,
'''  strictRuntimeValidation: boolean = false,
  stdin?: string
): Promise<StyleApplyResponse> {
''',
'''  strictRuntimeValidation: boolean = false,
  stdin?: string,
  stdinCases?: string[]
): Promise<StyleApplyResponse> {
''')
add(API,
'''  if (stdin !== undefined) {
    requestBody.stdin = stdin;
  }
''',
'''  if (stdin !== undefined) {
    requestBody.stdin = stdin;
  }
  // Optional batch stdin: each row is checked against the same code pair.
  if (stdinCases !== undefined && stdinCases.length > 0) {
    requestBody.stdin_cases = stdinCases;
  }
''')

HOOK="frontend/hooks/useStyleApplication.ts"
add(HOOK,
'''    strictRuntimeValidation: boolean = false,
    stdin?: string
  ) => {
''',
'''    strictRuntimeValidation: boolean = false,
    stdin?: string,
    stdinCases?: string[]
  ) => {
''')
add(HOOK,
'''        strictRuntimeValidation,
        stdin
      );
''',
'''        strictRuntimeValidation,
        stdin,
        stdinCases
      );
''')

UI="frontend/components/sections/StyleApplySection.tsx"
add(UI,
'''    legacyVerificationOption?: boolean,
    stdin?: string
''',
'''    legacyVerificationOption?: boolean,
    stdin?: string,
    stdinCases?: string[]
''')
add(UI,
'''    void handleApplyStyle(selected.functionCases, false, selected.stdin);
''',
'''    void handleApplyStyle(selected.functionCases, false, selected.stdin, selected.stdinCases);
''')
add(UI,
'''  const functionVerification =
    executionVerification?.function_verification;
''',
'''  const functionVerification =
    executionVerification?.function_verification;
  // CAPSTONE_BATCH37_MULTI_STDIN_V1: one real result pair per submitted stdin.
  const stdinCaseResults = executionVerification?.stdin_case_results ?? [];
''')
add(UI,
'''                            여러 테스트 중 첫 번째로 작성한 stdin을 기본 실행 비교에도 사용합니다.
                            함수별 입력은 해당 함수 테스트에서 각각 사용됩니다.
''',
'''                            입력한 각 stdin을 독립적으로 실행 비교하며, 결과는 테스트 개수만큼 표시됩니다.
                            함수별 입력은 해당 함수 테스트에서 각각 사용됩니다.
''')

# Preserve existing Before/After code viewers. Only the execution output
# bodies change from a single output to the verified batch entries.
BEFORE='''                    <ExecutionOutput
                      result={
                        executionVerification?.original
                      }
                      emptyMessage="변환 전 코드의 실행 결과를 확인할 수 없습니다."
                    />
'''
AFTER='''                    <ExecutionOutput
                      result={
                        executionVerification?.transformed
                      }
                      emptyMessage="스타일 적용 후 코드의 실행 결과를 확인할 수 없습니다."
                    />
'''

def batch_ui(which: str, fallback: str) -> str:
    return f'''                    {{stdinCaseResults.length > 0 ? (
                      <div className="space-y-4">
                        {{stdinCaseResults.map((test) => (
                          <div key={{test.case_number}} className="rounded-lg border border-slate-200 bg-white p-3">
                            <p className="mb-1 text-xs font-semibold text-slate-700">
                              입력 테스트 {{test.case_number}} / {{stdinCaseResults.length}} · {{test.status === "equivalent" ? "일치" : test.status === "different" ? "불일치" : "검증 불가"}}
                            </p>
                            <pre className="mb-3 whitespace-pre-wrap break-words font-mono text-xs text-slate-500">{{test.stdin}}</pre>
                            <ExecutionOutput
                              result={{test.{which}}}
                              emptyMessage="테스트 실행 결과를 확인할 수 없습니다."
                            />
                          </div>
                        ))}}
                      </div>
                    ) : (
                      <ExecutionOutput
                        result={{executionVerification?.{which}}}
                        emptyMessage="{fallback}"
                      />
                    )}}
'''
add(UI,BEFORE,batch_ui('original','변환 전 코드의 실행 결과를 확인할 수 없습니다.'))
add(UI,AFTER,batch_ui('transformed','스타일 적용 후 코드의 실행 결과를 확인할 수 없습니다.'))


def transform(path: str, source: str) -> tuple[str,bool]:
    changed = False
    for old,new,expected in PATCHES[path]:
        old_count=source.count(old)
        new_count=source.count(new)
        if new_count == expected:
            # already patched (some replacements intentionally preserve old text)
            pass
        elif old_count == expected and new_count == 0:
            source=source.replace(old,new,expected)
            changed=True
        else:
            raise ValueError(f'{path}: anchor mismatch or unexpected duplicates ({old_count} old, {new_count} new): {old[:70]!r}')
    return source,changed


def main():
    parser=argparse.ArgumentParser()
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check',action='store_true')
    action.add_argument('--apply',action='store_true')
    action.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    if not (ROOT/'frontend'/'package.json').is_file() or not (ROOT/'backend'/'app').is_dir():
        parser.error('Run this tool inside an extracted patch at the capstone_main root.')
    edits=[]
    for rel in PATCHES:
        path=ROOT/rel
        if not path.is_file():
            parser.error(f'Missing project file: {rel}')
        source=path.read_text(encoding='utf-8')
        try:
            target,changed=transform(rel,source)
        except ValueError as exc:
            parser.error(str(exc))
        edits.append((path,source,target,changed))
    if args.preview:
        for path,old,new,changed in edits:
            if changed:
                print(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile=str(path.relative_to(ROOT)),tofile=str(path.relative_to(ROOT)))))
        return
    if args.check:
        for path,_,_,changed in edits:
            print(f'{"ready" if changed else "already applied"}: {path.relative_to(ROOT)}')
        print(f'validated {len(edits)} source files; no changes made')
        return
    # All files validated above: nothing is written until every anchor passes.
    for path,_,target,changed in edits:
        if changed:
            path.write_text(target,encoding='utf-8')
            print('updated:',path.relative_to(ROOT))
        else:
            print('unchanged:',path.relative_to(ROOT))
    print('Batch stdin patch applied. Run tests and TypeScript checks before commit.')

if __name__ == '__main__': main()
