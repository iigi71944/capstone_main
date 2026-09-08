from pydantic import BaseModel
from typing import Optional, List, Dict, Any


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


class StyleApplyResponse(BaseModel):
    success: bool
    original_code: str
    transformed_code: str
    summary: Optional[str] = None
    applied_rules: List[str] = []
    warnings: List[str] = []
    error: Optional[str] = None