from fastapi import APIRouter
from app.schemas.improve_code import ImproveCodeRequest, ImproveCodeResponse
from app.services.improvement.improve_code_service import improve_code

router = APIRouter()


@router.post("/improve-code", response_model=ImproveCodeResponse)
def improve_code_api(request: ImproveCodeRequest):
    if request.language.lower() != "python":
        return ImproveCodeResponse(
            success=False,
            mode=request.mode,
            original_code=request.code,
            improved_code="",
            error="Python만 지원합니다."
        )

    try:
        improved_code, summary = improve_code(request.code, request.mode)

        return ImproveCodeResponse(
            success=True,
            mode=request.mode,
            original_code=request.code,
            improved_code=improved_code,
            summary=summary
        )

    except Exception as e:
        return ImproveCodeResponse(
            success=False,
            mode=request.mode,
            original_code=request.code,
            improved_code="",
            error=str(e)
        )