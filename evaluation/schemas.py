from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class TestCase(BaseModel):
    id: str
    query: str
    expected_doc_ids: list[str] = Field(default_factory=list, description="Retrieval 평가용 기대 문서 ID 목록")
    requirements: list[str] = Field(default_factory=list, description="Requirement Coverage 평가용 체크리스트")
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    test_case_id: str
    query: str
    
    # Retrieval Scores
    retrieval_precision: float = 0.0
    retrieved_sources: list[str] = Field(default_factory=list)
    
    # Generation Scores (LLM-based)
    faithfulness_score: float = 0.0
    faithfulness_reason: str = ""
    
    requirement_coverage_score: float = 0.0
    requirement_coverage_reason: str = ""
    
    # Rule-based Scores
    rule_score: float = 0.0
    rule_details: list[str] = Field(default_factory=list)
    
    # Overall
    total_score: float = 0.0
    generated_reply: str = ""
    has_doc_report: bool = False


class AggregateReport(BaseModel):
    total_cases: int
    avg_precision: float
    avg_faithfulness: float
    avg_coverage: float
    avg_rule_score: float
    avg_total_score: float
    results: list[EvaluationResult]
