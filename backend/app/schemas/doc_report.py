"""기술문서 분석 결과 스키마.

LLM이 생성한 구조화된 문서 분석 리포트를 표현한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DocSection(BaseModel):
    """문서 내 개별 섹션의 분석 결과."""
    title: str = Field(..., description="섹션 제목")
    summary: str = Field(..., description="섹션 요약 (1~3문장)")
    key_points: list[str] = Field(default_factory=list, description="핵심 포인트 목록")


class QAPair(BaseModel):
    """문서로부터 도출한 질문-답변 쌍."""
    question: str
    answer: str


class DocReport(BaseModel):
    """문서 분석 최종 리포트."""
    document_title: str = Field(..., description="문서 제목 (추정 또는 명시)")
    overall_summary: str = Field(..., description="전체 요약 (3~5문장)")
    sections: list[DocSection] = Field(default_factory=list, description="섹션별 분석")
    keywords: list[str] = Field(default_factory=list, description="핵심 키워드")
    qa_pairs: list[QAPair] = Field(default_factory=list, description="문서 기반 Q&A")
    references: list[str] = Field(default_factory=list, description="활용 출처")
