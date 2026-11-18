
"""Check observed Python execution behavior with optional function tests.

The existing subprocess-based runtime verification remains available.
When function cases are supplied, supported return values are also compared.

This runner is not a security sandbox. Only trusted local code should be
executed until a separately isolated execution environment is available.
"""

import ast
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Optional


DEFAULT_TIMEOUT_SECONDS = 2.0
MAX_OUTPUT_LENGTH = 10_000
# CAPSTONE_BATCH17_STDIN_V1: user-supplied input is bounded, never a sandbox.
MAX_STDIN_CHARS = 8192
MAX_STDIN_NEWLINES = 128
TRUNCATION_NOTICE = "\n...[출력 길이 제한으로 일부 생략됨]"


@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: Optional[int]
    timed_out: bool
    blocked: bool
    block_reason: Optional[str] = None


@dataclass
class ExecutionVerification:
    source: str
    status: str
    equivalent: Optional[bool]
    original: ExecutionResult
    transformed: ExecutionResult
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


BLOCKED_CALL_NAMES = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "breakpoint",
}

BLOCKED_MODULE_NAMES = {
    "os",
    "subprocess",
    "socket",
    "pathlib",
    "shutil",
    "sys",
    "ctypes",
    "multiprocessing",
    "threading",
    "asyncio",
    "http",
    "urllib",
    "requests",
}


def _trim_output(value: str) -> str:
    if len(value) <= MAX_OUTPUT_LENGTH:
        return value

    return value[:MAX_OUTPUT_LENGTH] + TRUNCATION_NOTICE


def valid_stdin_input(value: object) -> bool:
    """Bound user-provided stdin; type must be a real string."""
    return (type(value) is str and len(value) <= MAX_STDIN_CHARS
            and value.count("\n") <= MAX_STDIN_NEWLINES)


def _get_call_name(node: ast.Call) -> Optional[str]:
    if isinstance(node.func, ast.Name):
        return node.func.id

    return None


def _find_block_reason(code: str, *, allow_input: bool = False) -> Optional[str]:
    try:
        tree = ast.parse(code)

    except SyntaxError:
        return "Python 문법 오류가 있어 실행할 수 없습니다."

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                module_names = [
                    alias.name.split(".")[0]
                    for alias in node.names
                ]

            else:
                module_names = [
                    (node.module or "").split(".")[0]
                ]

            for module_name in module_names:
                if module_name in BLOCKED_MODULE_NAMES:
                    return (
                        f"실행 검증에서 허용하지 않는 모듈 "
                        f"'{module_name}'을(를) 사용하고 있습니다."
                    )

        if isinstance(node, ast.Call):
            call_name = _get_call_name(node)

            if call_name in BLOCKED_CALL_NAMES and not (
                allow_input and call_name == "input"
            ):
                return (
                    f"실행 검증에서 허용하지 않는 함수 "
                    f"'{call_name}'을(를) 사용하고 있습니다."
                )

        if isinstance(node, (ast.AsyncFunctionDef, ast.Await)):
            return (
                "비동기 실행 코드는 현재 자동 실행 "
                "검증 대상에서 제외됩니다."
            )

    return None


def _blocked_result(reason: str) -> ExecutionResult:
    return ExecutionResult(
        success=False,
        stdout="",
        stderr="",
        exit_code=None,
        timed_out=False,
        blocked=True,
        block_reason=reason,
    )


def execute_python_code(
    code: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    *,
    stdin: Optional[str] = None,
) -> ExecutionResult:
    """
    Python 코드를 별도 프로세스에서 실제 실행합니다.

    기존 실행 방식을 유지합니다.

    - Python 격리 모드(-I)
    - 표준 입력 차단
    - 실행 시간 제한
    - stdout, stderr 수집
    - 종료 코드 확인

    주의:
    subprocess와 -I만으로는 완전한 보안 격리가 불가능합니다.
    """

    # CAPSTONE_BATCH17_STDIN_V1: input() is permitted only with explicitly supplied stdin.
    if stdin is not None and not valid_stdin_input(stdin):
        return _blocked_result("표준 입력 길이 또는 형식 제한을 초과했습니다.")
    block_reason = (
        _find_block_reason(code) if stdin is None
        else _find_block_reason(code, allow_input=True)
    )

    if block_reason:
        return _blocked_result(block_reason)

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                code,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            **({"stdin": subprocess.DEVNULL} if stdin is None
               else {"input": stdin}),
        )

        return ExecutionResult(
            success=completed.returncode == 0,
            stdout=_trim_output(completed.stdout),
            stderr=_trim_output(completed.stderr),
            exit_code=completed.returncode,
            timed_out=False,
            blocked=False,
            block_reason=None,
        )

    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

        if isinstance(stdout, bytes):
            stdout = stdout.decode(
                "utf-8",
                errors="replace",
            )

        if isinstance(stderr, bytes):
            stderr = stderr.decode(
                "utf-8",
                errors="replace",
            )

        return ExecutionResult(
            success=False,
            stdout=_trim_output(stdout),
            stderr=_trim_output(stderr),
            exit_code=None,
            timed_out=True,
            blocked=False,
            block_reason=None,
        )

    except Exception as exc:
        return ExecutionResult(
            success=False,
            stdout="",
            stderr=str(exc),
            exit_code=None,
            timed_out=False,
            blocked=False,
            block_reason=None,
        )


def _normalize_output(value: str) -> str:
    return value.replace("\r\n", "\n")


def _output_truncated(result: ExecutionResult) -> bool:
    return (
        result.stdout.endswith(TRUNCATION_NOTICE)
        or result.stderr.endswith(TRUNCATION_NOTICE)
    )


def _exception_summary(stderr: str) -> str:
    lines = [
        line.strip()
        for line in stderr.splitlines()
        if line.strip()
    ]

    return lines[-1] if lines else ""


def _verification_result(
    status: str,
    equivalent: Optional[bool],
    original: ExecutionResult,
    transformed: ExecutionResult,
    message: str,
) -> dict:
    return ExecutionVerification(
        source="runtime",
        status=status,
        equivalent=equivalent,
        original=original,
        transformed=transformed,
        message=message,
    ).to_dict()


def _verify_observed_execution(
    original_code: str,
    transformed_code: str,
    stdin: Optional[str] = None,
) -> dict:
    """
    기존 실행 결과 비교 기능입니다.

    함수 테스트 입력이 없어도 기존과 동일하게 동작합니다.

    비교 항목:
    - 실행 차단
    - 시간 초과
    - 종료 코드
    - stdout
    - stderr
    - 예외 요약
    """

    if stdin is None:
        original = execute_python_code(original_code)
        transformed = execute_python_code(transformed_code)
    else:
        original = execute_python_code(original_code, stdin=stdin)
        transformed = execute_python_code(transformed_code, stdin=stdin)

    if original.blocked or transformed.blocked:
        reasons = []

        if original.block_reason:
            reasons.append(
                f"변환 전 코드: {original.block_reason}"
            )

        if transformed.block_reason:
            reasons.append(
                f"변환 후 코드: {transformed.block_reason}"
            )

        return _verification_result(
            status="not_verified",
            equivalent=None,
            original=original,
            transformed=transformed,
            message=" ".join(reasons),
        )

    if original.timed_out or transformed.timed_out:
        return _verification_result(
            status="not_verified",
            equivalent=None,
            original=original,
            transformed=transformed,
            message=(
                "실행 제한 시간을 초과해 전·후 코드의 "
                "결과를 비교하지 못했습니다."
            ),
        )

    if (
        original.exit_code is None
        or transformed.exit_code is None
    ):
        return _verification_result(
            status="not_verified",
            equivalent=None,
            original=original,
            transformed=transformed,
            message=(
                "코드 실행이 정상적으로 완료되지 않아 "
                "비교 결과를 확정할 수 없습니다."
            ),
        )

    if (
        _output_truncated(original)
        or _output_truncated(transformed)
    ):
        return _verification_result(
            status="not_verified",
            equivalent=None,
            original=original,
            transformed=transformed,
            message=(
                "실행 출력이 길이 제한으로 잘려 "
                "전체 결과의 동일성을 확인하지 못했습니다."
            ),
        )

    old_stdout = _normalize_output(original.stdout)
    new_stdout = _normalize_output(transformed.stdout)

    old_stderr = _normalize_output(original.stderr)
    new_stderr = _normalize_output(transformed.stderr)

    if original.exit_code != transformed.exit_code:
        return _verification_result(
            status="different",
            equivalent=False,
            original=original,
            transformed=transformed,
            message=(
                "변환 전·후 코드의 종료 코드가 "
                "서로 다릅니다."
            ),
        )

    if old_stdout != new_stdout:
        return _verification_result(
            status="different",
            equivalent=False,
            original=original,
            transformed=transformed,
            message=(
                "변환 전·후 코드의 표준 출력(stdout)이 "
                "서로 다릅니다."
            ),
        )

    if not original.success or not transformed.success:
        if (
            _exception_summary(old_stderr)
            != _exception_summary(new_stderr)
        ):
            return _verification_result(
                status="different",
                equivalent=False,
                original=original,
                transformed=transformed,
                message=(
                    "변환 전·후 코드의 예외 종류 "
                    "또는 메시지가 서로 다릅니다."
                ),
            )

        return _verification_result(
            status="not_verified",
            equivalent=None,
            original=original,
            transformed=transformed,
            message=(
                "두 코드가 오류로 종료했습니다. "
                "예외 요약이 같더라도 동작의 동일성은 "
                "확인되지 않았습니다."
            ),
        )

    if old_stderr != new_stderr:
        return _verification_result(
            status="different",
            equivalent=False,
            original=original,
            transformed=transformed,
            message=(
                "변환 전·후 코드의 표준 오류(stderr)가 "
                "서로 다릅니다."
            ),
        )

    if not old_stdout and not old_stderr:
        return _verification_result(
            status="not_verified",
            equivalent=None,
            original=original,
            transformed=transformed,
            message=(
                "두 코드 모두 정상 종료했지만 출력이 없어 "
                "함수 반환값이나 내부 상태의 동일성을 "
                "확인하지 못했습니다."
            ),
        )

    return _verification_result(
        status="equivalent",
        equivalent=True,
        original=original,
        transformed=transformed,
        message=(
            "이번 실행에서 종료 코드와 표준 출력·오류가 "
            "일치했습니다. 다른 입력의 함수 반환값이나 "
            "내부 상태까지 검증한 것은 아닙니다."
        ),
    )


def verify_execution_equivalence(
    original_code: str,
    transformed_code: str,
    function_cases: list[dict] | None = None,
    stdin: Optional[str] = None,
    stdin_cases: list[str] | None = None,
) -> dict:
    """
    변환 전후 코드의 실제 실행 결과를 비교합니다.

    function_cases가 None이면 기존 실행 검증만 수행합니다.

    function_cases가 제공되면:
    1. 기존 실행 결과를 먼저 비교합니다.
    2. 기본 실행에서 차이가 발견되면 different를 유지합니다.
    3. 기본 실행에 문제가 없다면 지정된 함수 테스트를 실행합니다.
    4. 반환값, 자료형, 출력 결과를 종합하여 판정합니다.

    예시:
        verify_execution_equivalence(
            original_code,
            transformed_code,
            function_cases=[
                {
                    "function": "calculate",
                    "args": [5],
                    "kwargs": {},
                }
            ],
        )

    equivalent는 관찰된 실행과 지정된 테스트 입력에서
    결과가 일치했다는 의미입니다.
    모든 가능한 입력에 대해 동등성을 보장하지 않습니다.
    """

    # CAPSTONE_BATCH37_MULTI_STDIN_V1: compare every submitted input against
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
    # 않으므로 이전과 동일한 반환 구조를 사용합니다.
    if function_cases is None:
        return result

    result["function_verification"] = None

    # Batch inputs are mandatory checks, not optional examples. A differing or
    # unverified stdin case must not be promoted to equivalent by function tests.
    if stdin_cases is not None and result["status"] != "equivalent":
        result["message"] += " 입력별 검증이 완료되지 않아 함수 테스트는 생략했습니다."
        return result

    # 이미 차이가 확인되었다면 추가 검증이 필요하지 않습니다.
    if result["status"] == "different":
        result["message"] += (
            " 출력 차이가 확인되어 함수 테스트는 생략했습니다."
        )

        return result

    original = result["original"]
    transformed = result["transformed"]

    # 기본 실행이 차단되었거나 실패했다면 함수 테스트가
    # 일부 성공하더라도 전체 결과를 검증 완료로 취급하지 않습니다.
    if not (
        original["success"]
        and transformed["success"]
        and not original["blocked"]
        and not transformed["blocked"]
        and not original["timed_out"]
        and not transformed["timed_out"]
        and original["exit_code"] == 0
        and transformed["exit_code"] == 0
        and not original["stdout"].endswith(TRUNCATION_NOTICE)
        and not transformed["stdout"].endswith(TRUNCATION_NOTICE)
        and not original["stderr"].endswith(TRUNCATION_NOTICE)
        and not transformed["stderr"].endswith(TRUNCATION_NOTICE)
    ):
        result["message"] += (
            " 기본 실행 검증이 완료되지 않아 "
            "함수 테스트를 생략했습니다."
        )

        return result

    # 순환 import 방지를 위해 함수 내부에서 가져옵니다.
    # function_result_validation_service는 이 파일의
    # execute_python_code를 사용합니다.
    from app.services.function_result_validation_service import (
        verify_function_results,
    )

    function_result = verify_function_results(
        original_code, transformed_code, function_cases,
        **({"stdin": stdin} if stdin is not None else {}),
    )

    result["function_verification"] = function_result
    result["source"] = "runtime+function_tests"

    # 출력이 같더라도 함수 반환값이 다르면 different입니다.
    if function_result["status"] == "different":
        result["status"] = "different"
        result["equivalent"] = False
        result["message"] = (
            "기본 실행 결과가 일치하더라도 지정된 함수 "
            "테스트에서 반환값·자료형·출력 차이를 확인했습니다."
        )

    # 함수 검증을 완료하지 못했다면 동일하다고 판단하지 않습니다.
    elif function_result["status"] == "not_verified":
        result["status"] = "not_verified"
        result["equivalent"] = None
        result["message"] = (
            "기본 실행과 지정된 함수 테스트 중 "
            "검증을 완료하지 못한 항목이 있어 "
            "동일성을 확정하지 않았습니다."
        )

    # 두 검증에서 관찰된 결과가 모두 일치한 경우입니다.
    else:
        result["status"] = "equivalent"
        result["equivalent"] = True
        result["message"] = (
            "기본 실행의 출력·종료 상태와 지정된 함수 "
            "입력에 대한 반환값·자료형·출력이 일치했습니다. "
            "검사하지 않은 입력과 내부 상태까지 "
            "동일함을 보장하지는 않습니다."
        )

    return result
