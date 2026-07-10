"""Pydantic 请求/响应数据模型"""
from pydantic import BaseModel, Field
from typing import Optional


class TagItem(BaseModel):
    label: str
    source: str = "free_text"  # free_text | question_answer | rule
    confidence: float = Field(ge=0.0, le=1.0)


class QuestionOption(BaseModel):
    label: str
    tag: Optional[str] = None


class Question(BaseModel):
    id: str
    text: str
    dimension: str
    strategy: str  # concretize | scenario | supplement
    options: list[QuestionOption]


# ─── 请求 ───

class AnalyzeRequest(BaseModel):
    free_text: str = Field(min_length=1, max_length=5000)
    demand_types: list[str] = Field(default_factory=list)
    question_history: list[dict] = Field(default_factory=list)
    draft_tags: dict[str, list[dict]] = Field(default_factory=dict)
    dimension_gaps: list[dict] = Field(default_factory=list)


class BioRequest(BaseModel):
    free_text: str = Field(min_length=1, max_length=5000)
    confirmed_tags: dict[str, list[str]]
    demand_types: list[str] = Field(default_factory=list)


class SaveProfileRequest(BaseModel):
    basic_fields: dict
    tags: dict[str, list[str]]
    bio: str


# ─── 响应 ───

class AnalyzeResponse(BaseModel):
    tags: dict[str, list[TagItem]]
    questions: list[Question]


class BioResponse(BaseModel):
    bio: str


class SaveProfileResponse(BaseModel):
    success: bool
    profile_id: str
    tag_count: int
    completeness_score: int = 0
