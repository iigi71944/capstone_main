from pydantic import BaseModel


class ImproveCodeRequest(BaseModel):
    language: str
    code: str
    mode: str


class ImproveCodeResponse(BaseModel):
    success: bool
    mode: str
    original_code: str
    improved_code: str
    summary: str | None = None
    error: str | None = None