import ast
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Optional


DEFAULT_TIMEOUT_SECONDS = 2.0
MAX_OUTPUT_LENGTH = 10_000


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

    return value[:MAX_OUTPUT_LENGTH] + "\n...[출력 길이 제한으로 일부 생략됨]"


def _get_call_name(node: ast.Call) -> Optional[str]:
    if isinstance(node.func, ast.Name):
        return node.func.id

    return None


def _find_block_reason(code: str) -> Optional[str]:
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

            if call_name in BLOCKED_CALL_NAMES:
                return (
                    f"실행 검증에서 허용하지 않는 함수 "
                    f"'{call_name}'을(를) 사용하고 있습니다."
                )

        if isinstance(node, (ast.AsyncFunctionDef, ast.Await)):
            return "비동기 실행 코드는 현재 자동 실행 검증 대상에서 제외됩니다."

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
) -> ExecutionResult:
    block_reason = _find_block_reason(code)

    if block_reason:
        return _blocked_result(block_reason)

    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            stdin=subprocess.DEVNULL,
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
            stdout = stdout.decode("utf-8", errors="replace")

        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")

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


def _normalize_stdout(value: str) -> str:
    return value.replace("\r\n", "\n").rstrip()


def verify_execution_equivalence(
    original_code: str,
    transformed_code: str,
) -> dict:
    original_result = execute_python_code(original_code)
    transformed_result = execute_python_code(transformed_code)

    if original_result.blocked or transformed_result.blocked:
        reasons = []

        if original_result.block_reason:
            reasons.append(
                f"변환 전 코드: {original_result.block_reason}"
            )

        if transformed_result.block_reason:
            reasons.append(
                f"변환 후 코드: {transformed_result.block_reason}"
            )

        verification = ExecutionVerification(
            source="runtime",
            status="not_verified",
            equivalent=None,
            original=original_result,
            transformed=transformed_result,
            message=" ".join(reasons),
        )

        return verification.to_dict()

    if original_result.timed_out or transformed_result.timed_out:
        verification = ExecutionVerification(
            source="runtime",
            status="not_verified",
            equivalent=None,
            original=original_result,
            transformed=transformed_result,
            message=(
                "실행 제한 시간을 초과하여 변환 전·후 코드의 "
                "동일성을 자동으로 검증하지 못했습니다."
            ),
        )

        return verification.to_dict()

    if not original_result.success or not transformed_result.success:
        verification = ExecutionVerification(
            source="runtime",
            status="not_verified",
            equivalent=None,
            original=original_result,
            transformed=transformed_result,
            message=(
                "변환 전 또는 변환 후 코드가 정상 종료되지 않아 "
                "실행 결과 동일성을 자동으로 검증하지 못했습니다."
            ),
        )

        return verification.to_dict()

    original_stdout = _normalize_stdout(original_result.stdout)
    transformed_stdout = _normalize_stdout(transformed_result.stdout)

    equivalent = original_stdout == transformed_stdout

    if equivalent:
        status = "equivalent"
        message = "변환 전·후 코드의 실행 출력이 동일합니다."
    else:
        status = "different"
        message = (
            "변환 전·후 코드의 실행 출력이 서로 달라 "
            "동일한 실행 결과로 판단할 수 없습니다."
        )

    verification = ExecutionVerification(
        source="runtime",
        status=status,
        equivalent=equivalent,
        original=original_result,
        transformed=transformed_result,
        message=message,
    )

    return verification.to_dict()