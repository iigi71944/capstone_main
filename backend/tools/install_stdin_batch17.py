"""Install Batch 17 stdin-aware saved-style verification (on top of Batch 16).

Read-only --check, strict preflight, CRLF/BOM preservation, rollback and backups.
All archive paths are ASCII for Windows PowerShell Expand-Archive.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path(__file__).resolve().parent / 'batch17_payload'
MARK = 'CAPSTONE_BATCH17_STDIN_V1'
PRIOR_MARK = 'CAPSTONE_BATCH16_STRICT_VERIFY_V1'
BASE_SHA = {
    'backend/app/services/execution_validation_service.py': 'f973f3e71ac76de1335184659497df167d488a12',
    'backend/app/services/function_result_validation_service.py': 'dfdc3f01553bdf6ea5118dbc8aa6c6b2dd4b7068',
    'backend/app/services/style_apply_service.py': '7fe2144586fd24439df2606e677a3054e53a5c70',
}
PRIOR_FILES = (
    'backend/app/schemas/style_apply.py',
    'backend/app/api/routes/style_apply.py',
    'frontend/types/analysis.ts',
    'frontend/lib/api.ts',
    'frontend/hooks/useStyleApplication.ts',
    'frontend/components/sections/StyleApplySection.tsx',
)
ALL = (*BASE_SHA, *PRIOR_FILES)
NEW_FILES = {
    'backend/tests/test_style_stdin_batch17.py': 'test_style_stdin_batch17.py.source',
    'backend/tools/audit_style_stdin_batch17.py': 'audit_style_stdin_batch17.py.source',
    'backend/tests/test_style_stdin_installer_batch17.py': 'test_style_stdin_installer_batch17.py.source',
}


def _sha(s: str) -> str:
    b = s.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()


def _read(path: Path) -> tuple[str, str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    value = raw.decode('utf-8-sig' if bom else 'utf-8')
    eol = '\r\n' if '\r\n' in value else '\n'
    return value.replace('\r\n', '\n'), eol, bom


def _replace(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f'{label}: expected one safe anchor; got {count}')
    return source.replace(before, after, 1)


def patch(path: str, src: str) -> str:
    r = lambda a, b, label: _replace(src, a, b, path + ' ' + label)
    if path == 'backend/app/services/execution_validation_service.py':
        src = _replace(src, 'MAX_OUTPUT_LENGTH = 10_000\n',
            'MAX_OUTPUT_LENGTH = 10_000\n'
            f'# {MARK}: user-supplied input is bounded, never a sandbox.\n'
            'MAX_STDIN_CHARS = 8192\nMAX_STDIN_NEWLINES = 128\n', path+' constants')
        src = _replace(src,
            'def _find_block_reason(code: str) -> Optional[str]:',
            'def _find_block_reason(code: str, *, allow_input: bool = False) -> Optional[str]:', path+' block signature')
        src = _replace(src, '            if call_name in BLOCKED_CALL_NAMES:\n',
            '            if call_name in BLOCKED_CALL_NAMES and not (\n'
            '                allow_input and call_name == "input"\n'
            '            ):\n', path+' block condition')
        src = _replace(src, 'def execute_python_code(\n    code: str,\n    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,\n) -> ExecutionResult:',
            'def execute_python_code(\n    code: str,\n    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,\n    *,\n    stdin: Optional[str] = None,\n) -> ExecutionResult:', path+' runner signature')
        src = _replace(src, '    block_reason = _find_block_reason(code)\n\n    if block_reason:',
            f'    # {MARK}: input() is permitted only with explicitly supplied stdin.\n'
            '    if stdin is not None and not valid_stdin_input(stdin):\n'
            '        return _blocked_result("표준 입력 길이 또는 형식 제한을 초과했습니다.")\n'
            '    block_reason = (\n'
            '        _find_block_reason(code) if stdin is None\n'
            '        else _find_block_reason(code, allow_input=True)\n'
            '    )\n\n    if block_reason:', path+' stdin policy')
        src = _replace(src, '            stdin=subprocess.DEVNULL,\n',
            '            **({"stdin": subprocess.DEVNULL} if stdin is None\n'
            '               else {"input": stdin}),\n', path+' subprocess stdin')
        src = _replace(src,
            'def _get_call_name(node: ast.Call) -> Optional[str]:',
            'def valid_stdin_input(value: object) -> bool:\n'
            '    """Bound user-provided stdin; type must be a real string."""\n'
            '    return (type(value) is str and len(value) <= MAX_STDIN_CHARS\n'
            '            and value.count("\\n") <= MAX_STDIN_NEWLINES)\n\n\n'
            'def _get_call_name(node: ast.Call) -> Optional[str]:', path+' validator')
        src = _replace(src, 'def _verify_observed_execution(\n    original_code: str,\n    transformed_code: str,\n) -> dict:',
            'def _verify_observed_execution(\n    original_code: str,\n    transformed_code: str,\n    stdin: Optional[str] = None,\n) -> dict:', path+' observed signature')
        src = _replace(src,
            '    original = execute_python_code(original_code)\n    transformed = execute_python_code(transformed_code)\n',
            '    if stdin is None:\n'
            '        original = execute_python_code(original_code)\n'
            '        transformed = execute_python_code(transformed_code)\n'
            '    else:\n'
            '        original = execute_python_code(original_code, stdin=stdin)\n'
            '        transformed = execute_python_code(transformed_code, stdin=stdin)\n',path+' observed calls')
        src = _replace(src, 'def verify_execution_equivalence(\n    original_code: str,\n    transformed_code: str,\n    function_cases: list[dict] | None = None,\n) -> dict:',
            'def verify_execution_equivalence(\n    original_code: str,\n    transformed_code: str,\n    function_cases: list[dict] | None = None,\n    stdin: Optional[str] = None,\n) -> dict:', path+' verify signature')
        src = _replace(src, '    result = _verify_observed_execution(\n        original_code,\n        transformed_code,\n    )\n',
            '    result = _verify_observed_execution(\n        original_code, transformed_code,\n        **({"stdin": stdin} if stdin is not None else {}),\n    )\n',path+' verify observed')
        src = _replace(src, '    function_result = verify_function_results(\n        original_code,\n        transformed_code,\n        function_cases,\n    )\n',
            '    function_result = verify_function_results(\n        original_code, transformed_code, function_cases,\n        **({"stdin": stdin} if stdin is not None else {}),\n    )\n',path+' function verify')
    elif path == 'backend/app/services/function_result_validation_service.py':
        src = _replace(src, 'from app.services.execution_validation_service import execute_python_code\n',
            'from app.services.execution_validation_service import (\n'
            '    execute_python_code, valid_stdin_input,\n)\n', path+' imports')
        src = _replace(src, '    return function_name, args, kwargs\n',
            '    case_stdin = case.get("stdin")\n'
            '    if case_stdin is not None and not valid_stdin_input(case_stdin):\n'
            '        raise ValueError("Function-test stdin exceeds limits or is not text.")\n'
            '    return function_name, args, kwargs\n',path+' validate case')
        src = _replace(src,
            'def _compare_case(\n    original_code: str,\n    transformed_code: str,\n    case: dict,\n) -> dict:',
            'def _compare_case(\n    original_code: str,\n    transformed_code: str,\n    case: dict,\n    stdin: str | None = None,\n) -> dict:',path+' case signature')
        src = _replace(src,
            '    # Each program runs in its own Python subprocess.\n'
            '    original = execute_python_code(original_program)\n'
            '    transformed = execute_python_code(transformed_program)\n',
            f'    # {MARK}: same stdin for both programs; case-specific override.\n'
            '    actual_stdin = case.get("stdin")\n'
            '    if actual_stdin is None:\n'
            '        actual_stdin = stdin\n'
            '    if actual_stdin is None:\n'
            '        original = execute_python_code(original_program)\n'
            '        transformed = execute_python_code(transformed_program)\n'
            '    else:\n'
            '        original = execute_python_code(original_program, stdin=actual_stdin)\n'
            '        transformed = execute_python_code(transformed_program, stdin=actual_stdin)\n',path+' case execution')
        src = _replace(src,
            'def verify_function_results(\n    original_code: str,\n    transformed_code: str,\n    cases: list[dict],\n) -> dict:',
            'def verify_function_results(\n    original_code: str,\n    transformed_code: str,\n    cases: list[dict],\n    stdin: str | None = None,\n) -> dict:',path+' result signature')
        src = _replace(src,
            '    # Validate all test inputs before executing any supplied code.\n',
            '    if stdin is not None and not valid_stdin_input(stdin):\n'
            '        raise ValueError("Shared stdin exceeds limits or is not text.")\n'
            '    # Validate all test inputs before executing any supplied code.\n',path+' validate global')
        src = _replace(src,
            '            case,\n        )\n        for case in cases\n',
            '            case,\n            **({"stdin": stdin} if stdin is not None else {}),\n        )\n        for case in cases\n',path+' call case')
    elif path == 'backend/app/services/style_apply_service.py':
        src = _replace(src,
            '    strict_runtime_validation: bool = False,\n):\n',
            '    strict_runtime_validation: bool = False,\n'
            '    stdin: str | None = None,\n):\n',path+' apply signature')
        src = _replace(src,
            '                function_cases=function_cases,\n            )\n',
            f'                function_cases=function_cases,\n'
            '                **({"stdin": stdin} if stdin is not None else {}),\n'
            '            )\n',path+' verifier call')
    elif path == 'backend/app/schemas/style_apply.py':
        src = _replace(src,
            'class FunctionTestCase(BaseModel):',
            'class FunctionTestCase(BaseModel):', path+' schema known') if False else src
        # Limited stdin per test; the old request shape remains valid.
        src = _replace(src,
            'class StyleApplyRequest(BaseModel):',
            f'    # {MARK}: optional stdin for this specific function call.\n'
            '    stdin: Optional[str] = Field(default=None, max_length=8192)\n\n\n'
            'class StyleApplyRequest(BaseModel):',path+' case stdin')
        src = _replace(src,
            '    strict_runtime_validation: bool = False\n',
            '    strict_runtime_validation: bool = False\n'
            f'    # {MARK}: shared stdin for base execution and function cases.\n'
            '    stdin: Optional[str] = Field(default=None, max_length=8192)\n',path+' request stdin')
    elif path == 'backend/app/api/routes/style_apply.py':
        src = _replace(src,
            '        strict_runtime_validation = getattr(request, "strict_runtime_validation", False)\n',
            '        strict_runtime_validation = getattr(request, "strict_runtime_validation", False)\n'
            f'        # {MARK}: legacy mocked requests may not have a stdin field.\n'
            '        stdin_input = getattr(request, "stdin", None)\n',path+' request')
        src = _replace(src,
            '            strict_runtime_validation=strict_runtime_validation,\n        )',
            '            strict_runtime_validation=strict_runtime_validation,\n'
            '            **({"stdin": stdin_input} if stdin_input is not None else {}),\n        )',path+' apply stdin')
        original = '                    function_cases=function_cases,\n                )\n'
        updated = ('                    function_cases=function_cases,\n'
                   '                    **({"stdin": stdin_input} if stdin_input is not None else {}),\n'
                   '                )\n')
        if src.count(original) != 2:
            raise RuntimeError(path + ': expected 2 post-format/cleanup calls')
        src = src.replace(original, updated, 2)
    elif path == 'frontend/types/analysis.ts':
        src = _replace(src,
            'export type FunctionTestCase = {\n',
            'export type FunctionTestCase = {\n  stdin?: string | null; // optional case-specific stdin\n',path+' type case')
        src = _replace(src,
            '  strict_runtime_validation?: boolean;\n',
            '  strict_runtime_validation?: boolean;\n'
            f'  // {MARK}: optional shared input text.\n'
            '  stdin?: string | null;\n',path+' type request')
    elif path == 'frontend/lib/api.ts':
        src = _replace(src,
            '  strictRuntimeValidation: boolean = false\n): Promise<StyleApplyResponse>',
            '  strictRuntimeValidation: boolean = false,\n'
            '  stdin?: string\n): Promise<StyleApplyResponse>',path+' args')
        src = _replace(src,
            '  if (strictRuntimeValidation) {\n    requestBody.strict_runtime_validation = true;\n  }\n',
            '  if (strictRuntimeValidation) {\n    requestBody.strict_runtime_validation = true;\n  }\n'
            f'  // {MARK}: omit shared stdin for legacy requests.\n'
            '  if (stdin !== undefined) {\n    requestBody.stdin = stdin;\n  }\n',path+' payload')
    elif path == 'frontend/hooks/useStyleApplication.ts':
        src = _replace(src,
            '    strictRuntimeValidation: boolean = false\n  ) => {',
            '    strictRuntimeValidation: boolean = false,\n'
            '    stdin?: string\n  ) => {',path+' hook args')
        src = _replace(src,
            '        strictRuntimeValidation\n      );',
            '        strictRuntimeValidation,\n        stdin\n      );',path+' hook pass')
    elif path == 'frontend/components/sections/StyleApplySection.tsx':
        src = _replace(src,
            '    strictRuntimeValidation?: boolean\n  ) => void | Promise<void>;',
            '    strictRuntimeValidation?: boolean,\n'
            '    stdin?: string\n  ) => void | Promise<void>;',path+' section props')
        src = _replace(src,
            '  kwargsText: string;\n',
            '  kwargsText: string;\n  stdinText: string;\n',path+' draft type')
        src = _replace(src,
            '  kwargsText: "{}",\n',
            '  kwargsText: "{}",\n  stdinText: "",\n',path+' draft default')
        # Remove the full example Python program; retain only input-shape examples.
        start = src.index('const KEYWORD_ARGUMENT_EXAMPLE = `')
        finish = src.index('`;\n', start) + 3
        src = src[:start] + src[finish:]
        src = _replace(src,
            '  const nextFunctionDraftId = useRef(2);',
            f'  // {MARK}: shared stdin is available even without function tests.\n'
            '  const [stdinText, setStdinText] = useState("");\n'
            '  const nextFunctionDraftId = useRef(2);',path+' shared stdin state')
        src = _replace(src,
            '      | "kwargsText",\n',
            '      | "kwargsText"\n      | "stdinText",\n',path+' update type')
        src = _replace(src,
            '      cases.push({\n        function: functionName,\n',
            '      if (draft.stdinText.length > 8192) {\n'
            '        setFunctionInputError(`${index + 1}번 함수 입력은 8192자를 넘을 수 없습니다.`);\n'
            '        return null;\n'
            '      }\n'
            '      cases.push({\n        function: functionName,\n'
            '        ...(draft.stdinText ? { stdin: draft.stdinText } : {}),\n',path+' case building')
        src = _replace(src,
            '      void handleApplyStyle(undefined, strictRuntimeValidation);',
            '      void handleApplyStyle(undefined, strictRuntimeValidation, stdinText || undefined);',path+' submit basic')
        src = _replace(src,
            '    void handleApplyStyle(cases, strictRuntimeValidation);',
            '    void handleApplyStyle(cases, strictRuntimeValidation,\n'
            '      stdinText || (cases.find((test) => Boolean(test.stdin))?.stdin || undefined));',path+' submit function')
        src = _replace(src,
            '          {/* ========================================= */}\n          {/* Step 03: 함수 반환값 검증 */}',
            f'          {{/* {MARK}: shared stdin for input() in program and functions */}}\n'
            '          <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-5">\n'
            '            <label htmlFor="shared-stdin" className="block text-sm font-semibold text-slate-900">\n'
            '              사용자 입력값 (stdin) <span className="font-normal text-slate-500">· 선택</span>\n'
            '            </label>\n'
            '            <p className="mt-2 text-xs leading-relaxed text-slate-600">\n'
            '              Python input()에서 입력받을 내용입니다. 입력값이 여러 개면 한 줄에 하나씩 작성해 주세요.\n'
            '              변환 전후 코드에 똑같이 전달하며, 함수 테스트에도 기본값으로 사용합니다.\n'
            '            </p>\n'
            '            <textarea id="shared-stdin" rows={3} maxLength={8192}\n'
            '              value={stdinText} disabled={styleApplyLoading}\n'
            '              onChange={(event) => { setStdinText(event.target.value); clearPreviousResult(); }}\n'
            '              placeholder={"5\\n10"}\n'
            '              className="mt-3 w-full resize-y rounded-lg border border-slate-300 bg-white p-3 font-mono text-sm text-slate-900"\n'
            '            />\n'
            '            <p className="mt-2 text-xs text-slate-500">예: 5 또는 첫째 줄 5, 둘째 줄 10.\n'
            '              함수 매개변수 [5]와 달리 대괄호 없이 입력합니다. 최대 8192자·129줄입니다.\n'
            '            </p>\n'
            '          </div>\n\n'
            '          {/* ========================================= */}\n          {/* Step 03: 함수 반환값 검증 */}',path+' shared UI')
        # Insert per-case stdin after kwargs field, before closing card grid.
        anchor = '                          {/* 실제 Python 코드 예시 */}'
        first = src.index(anchor)
        # Pair off the *whole* old card, including example and explanatory program snippet.
        stop = src.index('\n                        </div>\n                      </div>\n                    </div>', first)
        src = src[:first] + '''                        </div>

                        {/* 사용자 입력값: 이 함수 테스트에만 적용하는 override */}
                        <div className="lg:col-span-2">
                          <label htmlFor={`function-stdin-${draft.id}`}
                            className="mb-2 block text-xs font-semibold text-slate-700">
                            이 함수 테스트의 사용자 입력값 (stdin) <span className="font-normal text-slate-400">· 선택</span>
                          </label>
                          <textarea id={`function-stdin-${draft.id}`} rows={2} maxLength={8192}
                            value={draft.stdinText} disabled={styleApplyLoading}
                            onChange={(event) => updateFunctionDraft(draft.id, "stdinText", event.target.value)}
                            placeholder={"5\\n10"}
                            className="w-full resize-y rounded-lg border border-slate-300 bg-white p-3 font-mono text-sm text-slate-900"
                          />
                          <p className="mt-2 text-xs leading-relaxed text-slate-500">
                            입력 예: 5 (한 번), 5와 10 (두 줄). 비워두면 위의 공통 stdin을 사용합니다.
                            공통 입력이 비어 있으면 첫 번째 개별 입력을 기본 실행에도 사용합니다.
                          </p>
                        </div>
''' + src[stop+len('\n                        </div>'):]
    else:
        raise ValueError('Unknown patch target: ' + path)
    return src


def _encode(source: str, eol: str, bom: bool) -> bytes:
    data = source.replace('\n', eol).encode('utf-8')
    return (b'\xef\xbb\xbf' if bom else b'') + data


def build_changes(root: Path = ROOT) -> tuple[dict[Path, bytes], str]:
    result: dict[Path, bytes] = {}
    state = []
    for path in ALL:
        full = root / path
        if not full.is_file():
            raise RuntimeError('Required file is missing: ' + path)
        source, eol, bom = _read(full)
        done = MARK in source
        state.append(done)
        if done:
            continue
        if path in BASE_SHA:
            if _sha(source) != BASE_SHA[path]:
                raise RuntimeError('Unexpected source version, aborting: ' + path)
        elif PRIOR_MARK not in source:
            raise RuntimeError('Install Batch 16 first; missing marker in: ' + path)
        changed = patch(path, source)
        if changed == source:
            raise RuntimeError('No modifications in: ' + path)
        if path.endswith('.py'):
            ast.parse(changed, filename=path)
        result[full] = _encode(changed, eol, bom)

    for path, name in NEW_FILES.items():
        full = root / path
        payload = PAYLOAD / name
        if not payload.is_file():
            raise RuntimeError('Missing test payload: ' + name)
        new_bytes = payload.read_bytes()
        if full.exists():
            if full.read_bytes() != new_bytes:
                raise RuntimeError('Unexpected existing file: ' + path)
        else:
            result[full] = new_bytes
    if all(state) and not result:
        return {}, 'already_installed'
    if any(state):
        raise RuntimeError('Partial Batch 17 installation detected; no files changed')
    return result, 'ready'


def install(root: Path = ROOT, check: bool = False) -> str:
    changes, status = build_changes(root)
    if check or status == 'already_installed':
        return f'{status}: {len(changes)} file changes planned'
    git_dir = root / '.git'
    if not git_dir.is_dir():
        raise RuntimeError('No .git directory; installation aborted')
    backup = git_dir / 'capstone_batch17_backups'
    if backup.exists():
        raise RuntimeError('Batch 17 backup already exists; investigate before retrying')
    backup.mkdir(parents=True)
    original = {}
    try:
        for path in changes:
            if path.is_file():
                old = path.read_bytes()
                original[path] = old
                dest = backup / path.relative_to(root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(old)
        for path, data in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.capstone17-')
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
    except Exception:
        for path in changes:
            if path in original:
                path.write_bytes(original[path])
            elif path.exists():
                path.unlink()
        raise
    return f'installed: {len(changes)} files; backups in {backup}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(install(check=args.check))


if __name__ == '__main__':
    main()
