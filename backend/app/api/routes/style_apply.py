from fastapi import APIRouter

from app.schemas.style_apply import StyleApplyRequest, StyleApplyResponse
from app.services.style_apply_service import apply_coding_style


router = APIRouter()


@router.post("/apply-style", response_model=StyleApplyResponse)
def apply_style_api(request: StyleApplyRequest):
    if request.language.lower() != "python":
        return StyleApplyResponse(
            success=False,
            original_code=request.code,
            transformed_code="",
            applied_rules=[],
            warnings=[],
            error="현재는 Python만 지원합니다."
        )

    try:
        transformed_code, summary, applied_rules, warnings = apply_coding_style(
            code=request.code,
            style=request.style.model_dump(),
        )

        return StyleApplyResponse(
            success=True,
            original_code=request.code,
            transformed_code=transformed_code,
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
            applied_rules=[],
            warnings=[],
            error=f"문법 오류: {e.msg} (line {e.lineno})"
        )

    except Exception as e:
        return StyleApplyResponse(
            success=False,
            original_code=request.code,
            transformed_code="",
            applied_rules=[],
            warnings=[],
            error=f"스타일 적용 중 오류 발생: {str(e)}"
        )