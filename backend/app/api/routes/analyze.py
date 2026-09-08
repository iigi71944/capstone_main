from fastapi import APIRouter
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from app.services.parser_service import parse_code
from app.services.syntax_tag_service import extract_syntax_tags
from app.services.metric_service import calculate_metrics
from app.services.highlight_service import extract_highlights
from app.services.concept_tag_service import extract_concept_tags

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
            highlights=[],
            suggestions=[],
            error="현재는 Python만 지원합니다."
        )

    try:
        tree = parse_code(request.code)
        syntax_tags = extract_syntax_tags(tree)
        metrics = calculate_metrics(tree)
        concept_tags = extract_concept_tags(metrics)
        highlights = extract_highlights(tree)

        return AnalyzeResponse(
            success=True,
            syntax_tags=syntax_tags,
            concept_tags=concept_tags,
            metrics=metrics,
            highlights=highlights,
            suggestions=[],
            error=None
        )

    except SyntaxError as e:
        return AnalyzeResponse(
            success=False,
            syntax_tags=[],
            concept_tags=[],
            metrics={},
            highlights=[],
            suggestions=[],
            error=f"문법 오류: {e.msg} (line {e.lineno})"
        )

    except Exception as e:
        return AnalyzeResponse(
            success=False,
            syntax_tags=[],
            concept_tags=[],
            metrics={},
            highlights=[],
            suggestions=[],
            error=f"분석 중 오류 발생: {str(e)}"
        )