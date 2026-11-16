
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Coding style data
# ============================================================

class StyleTagItem(BaseModel):
    tag: str
    count: Optional[int] = None
    score: Optional[float] = None
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None  # CAPSTONE_FORMAT_CONCEPT_SCHEMA_V1


class CodingStylePayload(BaseModel):
    id: str
    name: str
    description: str
    syntax_tags: List[StyleTagItem]
    concept_tags: List[StyleTagItem]
    metrics: Dict[str, int]
    created_at: str

    # CAPSTONE_SAVED_FORMAT_APPLY_V1: 기존 스타일 JSON의 서식 프로필을 보존
    formatting_style: Optional[Dict[str, Any]] = None


# ============================================================
# Function test request
# ============================================================

class FunctionTestCase(BaseModel):
    """
    함수 반환값 검증에 사용할 테스트 입력입니다.

    예시:
        {
            "function": "calculate",
            "args": [5],
            "kwargs": {}
        }

    args와 kwargs를 생략하면 빈 인자로 호출합니다.

    입력값의 세부 자료형 제한은
    function_result_validation_service.py에서 검사합니다.
    """

    function: str

    args: List[Any] = Field(
        default_factory=list
    )

    kwargs: Dict[str, Any] = Field(
        default_factory=dict
    )


    # CAPSTONE_BATCH17_STDIN_V1: optional stdin for this specific function call.
    stdin: Optional[str] = Field(default=None, max_length=8192)


class StyleApplyRequest(BaseModel):
    language: str
    code: str
    style: CodingStylePayload

    # 기존 API 요청과의 호환성을 유지합니다.
    # None이면 기존 stdout 기반 검증만 수행합니다.
    #
    # 함수 검증 요청은 1~8개만 허용합니다.
    function_cases: Optional[List[FunctionTestCase]] = Field(
        default=None,
        min_length=1,
        max_length=8,
    )

    # CAPSTONE_BATCH16_STRICT_VERIFY_V1: opt-in; old clients remain permissive.
    strict_runtime_validation: bool = False
    # CAPSTONE_BATCH17_STDIN_V1: shared stdin for base execution and function cases.
    stdin: Optional[str] = Field(default=None, max_length=8192)


# ============================================================
# Final code analysis
# ============================================================

class FinalAnalysis(BaseModel):
    syntax_tags: List[StyleTagItem] = Field(
        default_factory=list
    )

    concept_tags: List[StyleTagItem] = Field(
        default_factory=list
    )

    metrics: Dict[str, int] = Field(
        default_factory=dict
    )


# ============================================================
# Runtime execution results
# ============================================================

class ExecutionResult(BaseModel):
    success: bool

    stdout: str = ""
    stderr: str = ""

    exit_code: Optional[int] = None

    timed_out: bool = False
    blocked: bool = False

    block_reason: Optional[str] = None


# ============================================================
# Function verification results
# ============================================================

class FunctionCaseVerification(BaseModel):
    """
    함수 테스트 한 건의 실행 검증 결과입니다.

    status:
        equivalent
        different
        not_verified
    """

    function: str

    args: List[Any] = Field(
        default_factory=list
    )

    kwargs: Dict[str, Any] = Field(
        default_factory=dict
    )

    status: str

    equivalent: Optional[bool] = None

    message: str = ""

    # Observed records returned by the function-test harness.
    # None means execution was blocked or a result was unavailable.
    original_result: Optional[Dict[str, Any]] = None
    transformed_result: Optional[Dict[str, Any]] = None
    original_stdout: Optional[str] = None
    transformed_stdout: Optional[str] = None


class FunctionVerification(BaseModel):
    """
    여러 함수 테스트를 종합한 검증 결과입니다.

    하나라도 결과 차이가 있으면 different,
    차이가 없지만 검증 불가능한 사례가 있으면 not_verified,
    모든 사례가 일치하면 equivalent입니다.
    """

    status: str

    equivalent: Optional[bool] = None

    cases: List[FunctionCaseVerification] = Field(
        default_factory=list
    )

    message: str = ""


# ============================================================
# Combined execution verification
# ============================================================

class ExecutionVerification(BaseModel):
    """
    기존 실행 결과 검증과 함수 반환값 검증을 함께 표현합니다.

    source:
        runtime
        runtime+function_tests

    function_verification은 선택 사항입니다.
    기존 API 응답에도 호환되도록 기본값을 None으로 둡니다.
    """

    source: str

    status: str

    equivalent: Optional[bool] = None

    original: ExecutionResult

    transformed: ExecutionResult

    message: str

    function_verification: Optional[FunctionVerification] = None


# ============================================================
# Style application response
# ============================================================

class StyleApplyResponse(BaseModel):
    success: bool

    original_code: str
    transformed_code: str

    final_analysis: Optional[FinalAnalysis] = None

    missing_syntax_tags: List[StyleTagItem] = Field(
        default_factory=list
    )

    missing_concept_tags: List[StyleTagItem] = Field(
        default_factory=list
    )

    execution_verification: Optional[ExecutionVerification] = None

    summary: Optional[str] = None

    applied_rules: List[str] = Field(
        default_factory=list
    )

    warnings: List[str] = Field(
        default_factory=list
    )

    error: Optional[str] = None
