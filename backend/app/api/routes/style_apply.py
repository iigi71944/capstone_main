
from fastapi import APIRouter

from app.schemas.style_apply import (
    StyleApplyRequest,
    StyleApplyResponse,
)
from app.services.style_apply_service import apply_coding_style


router = APIRouter()


@router.post(
    "/apply-style",
    response_model=StyleApplyResponse,
)
def apply_style_api(request: StyleApplyRequest):
    """
    저장된 코딩 스타일을 대상 Python 코드에 적용합니다.

    function_cases가 전달되지 않으면:
        기존 실행 결과 비교만 수행합니다.

    function_cases가 전달되면:
        기존 실행 결과 비교와 함께
        지정된 함수의 반환값 및 자료형도 검증합니다.

    실행 결과에 차이가 발견되면 style_apply_service에서
    변환을 취소하고 원본 코드를 유지합니다.
    """

    if request.language.lower() != "python":
        return StyleApplyResponse(
            success=False,
            original_code=request.code,
            transformed_code="",
            final_analysis=None,
            missing_syntax_tags=[],
            missing_concept_tags=[],
            execution_verification=None,
            applied_rules=[],
            warnings=[],
            error="현재는 Python만 지원합니다.",
        )

    try:
        # 기존 API 요청은 function_cases가 None입니다.
        # 함수 테스트가 전달된 경우에만 딕셔너리 형태로 변환합니다.
        function_cases = (
            [
                case.model_dump()
                for case in request.function_cases
            ]
            if request.function_cases is not None
            else None
        )

        (
            transformed_code,
            summary,
            applied_rules,
            warnings,
            final_diff,
            execution_verification,
        ) = apply_coding_style(
            code=request.code,
            style=request.style.model_dump(),
            function_cases=function_cases,
        )

        return StyleApplyResponse(
            success=True,
            original_code=request.code,
            transformed_code=transformed_code,
            final_analysis=final_diff.get("target_analysis"),
            missing_syntax_tags=final_diff.get(
                "missing_syntax_tags",
                [],
            ),
            missing_concept_tags=final_diff.get(
                "missing_concept_tags",
                [],
            ),
            execution_verification=execution_verification,
            summary=summary,
            applied_rules=applied_rules,
            warnings=warnings,
            error=None,
        )

    except SyntaxError as e:
        return StyleApplyResponse(
            success=False,
            original_code=request.code,
            transformed_code="",
            final_analysis=None,
            missing_syntax_tags=[],
            missing_concept_tags=[],
            execution_verification=None,
            applied_rules=[],
            warnings=[],
            error=(
                f"문법 오류: {e.msg} "
                f"(line {e.lineno})"
            ),
        )

    except Exception as e:
        return StyleApplyResponse(
            success=False,
            original_code=request.code,
            transformed_code="",
            final_analysis=None,
            missing_syntax_tags=[],
            missing_concept_tags=[],
            execution_verification=None,
            applied_rules=[],
            warnings=[],
            error=(
                "스타일 적용 중 오류 발생: "
                f"{str(e)}"
            ),
        )
