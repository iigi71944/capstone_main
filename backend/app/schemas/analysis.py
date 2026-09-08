from pydantic import BaseModel
from typing import List, Optional, Dict


class AnalyzeRequest(BaseModel):
    language: str
    code: str


class SyntaxTagItem(BaseModel):
    tag: str
    count: Optional[int] = None


class AnalyzeResponse(BaseModel):
    success: bool
    syntax_tags: List[SyntaxTagItem]
    concept_tags: List[dict]
    metrics: Dict[str, int]
    highlights: List[dict]
    suggestions: List[dict]
    error: Optional[str] = None