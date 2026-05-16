from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .doc_report import DocReport


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    uploaded_document: str | None = Field(
        default=None,
        description="사용자가 업로드한 기술문서의 텍스트 내용 (분석 시 주요 입력으로 활용)",
    )


class ToolTrace(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_preview: str | None = None


class ChatResponse(BaseModel):
    reply: str
    complete: bool
    doc_report: DocReport | None = None
    tool_trace: list[ToolTrace] = Field(default_factory=list)
