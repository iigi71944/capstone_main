from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class StyleTagItem(BaseModel):
    tag: str
    count: Optional[int] = None
    score: Optional[float] = None
    reason: Optional[str] = None


class CodingStylePayload(BaseModel):
    id: str
    name: str
    description: str
    syntax_tags: List[StyleTagItem]
    concept_tags: List[StyleTagItem]
    metrics: Dict[str, int]
    created_at: str


class StyleApplyRequest(BaseModel):
    language: str
    code: str
    style: CodingStylePayload


class FinalAnalysis(BaseModel):
    syntax_tags: List[StyleTagItem] = Field(default_factory=list)
    concept_tags: List[StyleTagItem] = Field(default_factory=list)
    metrics: Dict[str, int] = Field(default_factory=dict)


class StyleApplyResponse(BaseModel):
    success: bool
    original_code: str
    transformed_code: str

    final_analysis: Optional[FinalAnalysis] = None
    missing_syntax_tags: List[StyleTagItem] = Field(default_factory=list)
    missing_concept_tags: List[StyleTagItem] = Field(default_factory=list)

    summary: Optional[str] = None
    applied_rules: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None