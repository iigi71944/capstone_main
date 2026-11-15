from app.services.style_analysis_comment_filter_service import without_analysis_comments
from fastapi import APIRouter

from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from app.services.parser_service import parse_code
from app.services.syntax_tag_service import extract_syntax_tags
from app.services.metric_service import calculate_metrics
from app.services.concept_tag_service import extract_concept_tags
# CAPSTONE_FORMAT_CONCEPT_API_V1
from app.services.style_format_concept_tag_service import build_formatting_concept_tags


router = APIRouter()


@router.get("/ping")
def ping():
    return {"message": "analyze router ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_code(request: AnalyzeRequest):
    if request.language.lower() != "python":
        return AnalyzeResponse(
            success=False,
            syntax_tags=[],
            concept_tags=[],
            metrics={},
            suggestions=[],
            error="현재는 Python만 지원합니다."
        )

    try:
        tree = without_analysis_comments(parse_code(request.code))
        syntax_tags = extract_syntax_tags(tree)
        metrics = calculate_metrics(tree)
        concept_tags = extract_concept_tags(metrics)

        return AnalyzeResponse(
            success=True,
            syntax_tags=syntax_tags,
            concept_tags=concept_tags,
            metrics=metrics,
            suggestions=[],
            error=None
        )

    except SyntaxError as e:
        return AnalyzeResponse(
            success=False,
            syntax_tags=[],
            concept_tags=[],
            metrics={},
            suggestions=[],
            error=f"문법 오류: {e.msg} (line {e.lineno})"
        )

    except Exception as e:
        return AnalyzeResponse(
            success=False,
            syntax_tags=[],
            concept_tags=[],
            metrics={},
            suggestions=[],
            error=f"분석 중 오류 발생: {str(e)}"
        )


# CAPSTONE_FORMATTING_STYLE_GIT_ALIGNED_V2: 원본 코드 수정 없이 서식 정보만 반환합니다.
from pydantic import BaseModel as _FormattingStyleBaseModel
from app.services.style_format_profile_service import extract_formatting_style as _extract_formatting_style

class _FormattingStyleRequest(_FormattingStyleBaseModel):
    code: str

@router.post("/formatting-style")
def _analyze_formatting_style(request: _FormattingStyleRequest):
    try:
        profile = _extract_formatting_style(request.code)
    except SyntaxError:
        return {"success": False, "formatting_style": None, "error": "Python 문법 오류가 있습니다."}
    return {"success": True, "formatting_style": profile,
            "concept_tags": build_formatting_concept_tags(profile)}
