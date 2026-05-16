"""Single-agent ReAct loop using OpenAI tool-calling.

기술문서 분석 에이전트:
- 업로드된 문서를 주요 입력으로 사용
- rag_search / web_search 로 배경 지식 보강
- analyze_document 로 구조화된 DocReport 생성
- 모델이 어떤 툴을 호출할지 스스로 결정 (ReAct 방식)
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from .config import settings
from .schemas.chat import ChatMessage, ChatResponse, ToolTrace
from .schemas.curriculum import DocReport
from .tools import TOOL_REGISTRY, TOOL_SPECS


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    path = settings.prompts_path / "system_prompt.txt"
    return path.read_text(encoding="utf-8")


def _preview(text: str, limit: int = 280) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _build_initial_messages(
    history: list[ChatMessage],
    user_message: str,
    uploaded_document: str | None = None,
) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": _system_prompt()}]
    if uploaded_document and uploaded_document.strip():
        messages.append({
            "role": "system",
            "content": (
                "[사용자 업로드 문서]\n"
                "아래 문서는 사용자가 직접 업로드한 기술문서입니다. "
                "분석 시 이 내용을 최우선 입력으로 활용하고, "
                "analyze_document 호출 시 document_content 파라미터에 이 전체 내용을 그대로 전달하십시오.\n\n"
                f"{uploaded_document.strip()}"
            ),
        })
    for m in history[-8:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": user_message})
    return messages


def run_agent(
    user_message: str,
    history: list[ChatMessage],
    uploaded_document: str | None = None,
) -> ChatResponse:
    """Drive the tool-calling loop until the model produces a final reply."""
    messages = _build_initial_messages(history, user_message, uploaded_document)
    tool_trace: list[ToolTrace] = []

    doc_report: DocReport | None = None
    client = _client()

    for _step in range(settings.max_agent_steps):
        resp = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            tools=TOOL_SPECS,
            tool_choice="auto",
            temperature=0.2,
        )
        choice = resp.choices[0]
        msg = choice.message

        # Persist the assistant turn so subsequent tool messages have a parent.
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or "",
        }
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
        messages.append(assistant_msg)

        # No tool calls → model has produced its final reply.
        if not msg.tool_calls:
            return ChatResponse(
                reply=(msg.content or "").strip() or "응답을 생성하지 못했습니다.",
                complete=True,
                doc_report=doc_report,
                tool_trace=tool_trace,
            )

        for call in msg.tool_calls:
            name = call.function.name
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            handler = TOOL_REGISTRY.get(name)
            if handler is None:
                tool_output = json.dumps({"error": f"unknown tool: {name}"})
            else:
                # analyze_document 호출 시 업로드 문서 내용 자동 주입
                if name == "analyze_document" and uploaded_document and uploaded_document.strip():
                    arguments.setdefault("document_content", uploaded_document.strip())
                tool_output = handler(arguments)

            # analyze_document 결과를 DocReport로 파싱해 응답 페이로드에 포함
            if name == "analyze_document":
                try:
                    doc_report = DocReport.model_validate_json(tool_output)
                except (ValidationError, Exception):
                    doc_report = None

            tool_trace.append(
                ToolTrace(
                    name=name,
                    arguments=arguments,
                    result_preview=_preview(tool_output),
                )
            )

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": tool_output,
            })

    # Safety net: loop budget exhausted.
    return ChatResponse(
        reply="최대 단계 수를 초과했습니다. 요청을 더 구체적으로 작성하거나 문서를 업로드한 뒤 다시 시도해 주세요.",
        complete=False,
        doc_report=doc_report,
        tool_trace=tool_trace,
    )
