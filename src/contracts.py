"""Frozen integration contracts shared by all four development lanes."""

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]
Action = Literal["allow", "redact", "private", "block"]


class PageText(BaseModel):
    page: int = Field(ge=1)
    text: str


class IngestionResult(BaseModel):
    document_id: str
    input_type: Literal["text", "pdf", "image", "code"]
    filename: str | None = None
    language: Literal["ar", "en", "mixed", "unknown"] = "unknown"
    text: str
    pages: list[PageText] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SensitiveEntity(BaseModel):
    entity_type: str
    value: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    source: Literal["regex", "hf_ner", "secret_scanner"]
    severity: Literal["medium", "high", "critical"]
    page: int | None = Field(default=None, ge=1)


class ModelMetadata(BaseModel):
    detector: str
    classifier: str


class AnalysisResult(BaseModel):
    document_id: str
    entities: list[SensitiveEntity] = Field(default_factory=list)
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    recommended_action: Action
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str
    model_metadata: ModelMetadata


class Replacement(BaseModel):
    placeholder: str
    entity_type: str
    original_value: str


class RedactionResult(BaseModel):
    original_text: str
    safe_text: str
    replacements: list[Replacement] = Field(default_factory=list)


class FinalResponse(BaseModel):
    status: Literal["completed", "blocked", "error"]
    action_taken: Action
    analysis: AnalysisResult
    redaction: RedactionResult | None = None
    model_response: str | None = None
    user_message: str
    latency_ms: int = Field(ge=0)

