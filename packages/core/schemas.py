"""Data contracts and schemas for the scoring engine and probing pipeline."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class ComponentStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class ScoreComponent(BaseModel):
    """Evaluation result for an individual readiness signal."""

    name: str = Field(..., description="Machine-readable name of the check")
    display_name: str = Field(..., description="Human-readable title")
    score: float = Field(..., ge=0.0, le=100.0, description="Normalized score from 0 to 100")
    weight: float = Field(..., ge=0.0, le=1.0, description="Relative weight in overall calculation")
    status: ComponentStatus = Field(..., description="Status assessment based on score")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Structured inspection findings")
    details: str = Field("", description="Human-readable explanation of findings")
    recommendations: List[str] = Field(default_factory=list, description="Actionable remediation steps")


class Score(BaseModel):
    """Aggregated agent-readiness score for a website or URL."""

    url: str = Field(..., description="The target URL analyzed")
    version: str = Field(default="score_v0.1", description="Semantic algorithm version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Analysis timestamp in UTC",
    )
    overall_score: float = Field(..., ge=0.0, le=100.0, description="Weighted composite score (0-100)")
    grade: str = Field(..., description="Letter grade (A+, A, B, C, D, F)")
    components: List[ScoreComponent] = Field(..., description="Detailed component breakdown")
    summary: str = Field("", description="Executive summary of agent readiness")
    recommendations: List[str] = Field(default_factory=list, description="Prioritized recommendations")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution and response metadata")

    @field_validator("grade", mode="before")
    @classmethod
    def compute_grade_if_missing(cls, v: Any, info: Any) -> str:
        if v:
            return str(v)
        # Grade will be computed in scorer if omitted
        return "N/A"


class ProbeResult(BaseModel):
    """Raw and parsed output from an LLM citation probe."""

    provider: str = Field(..., description="Provider name (e.g. openai, anthropic, gemini, perplexity)")
    prompt: str = Field(..., description="Query prompt sent to the model")
    raw_response: str = Field(..., description="Unmodified response text verbatim")
    cited_domains: List[str] = Field(default_factory=list, description="Extracted domain citations")
    extracted_urls: List[str] = Field(default_factory=list, description="Extracted specific URLs")
    latency_ms: Optional[float] = Field(None, description="Response latency in milliseconds")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Probe timestamp in UTC",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider model and token usage metadata")
