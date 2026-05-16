"""기술문서 분석 툴 — 업로드된 문서와 검색 결과를 바탕으로 DocReport를 생성한다.

LLM structured output을 사용해 검증된 JSON 페이로드를 반환한다.
"""
from __future__ import annotations

import json
from functools import lru_cache

from openai import OpenAI
from pydantic import ValidationError

from ..config import settings
from ..schemas.doc_report import DocReport

ANALYZE_DOCUMENT_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_document",
        "description": (
            "업로드된 기술문서 또는 검색 결과를 바탕으로 구조화된 문서 분석 리포트(JSON)를 생성한다. "
            "문서 요약, 섹션별 분석, 핵심 키워드, Q&A 쌍을 포함한다. "
            "사용자가 문서를 업로드한 경우 document_content를 반드시 전달한다. "
            "RAG/웹 검색으로 보강한 내용이 있으면 context_summary에 담는다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_content": {
                    "type": "string",
                    "description": (
                        "사용자가 업로드한 기술문서의 전체 텍스트. "
                        "분석의 주요 입력으로 사용된다. "
                        "문서가 없는 경우 빈 문자열로 설정한다."
                    ),
                    "default": "",
                },
                "query": {
                    "type": "string",
                    "description": "사용자의 원본 질의 또는 분석 요청 내용",
                },
                "context_summary": {
                    "type": "string",
                    "description": "RAG/웹 검색에서 추출한 보강 컨텍스트 요약. 없으면 빈 문자열.",
                    "default": "",
                },
                "analysis_type": {
                    "type": "string",
                    "enum": ["summary", "qa", "keywords", "full"],
                    "description": (
                        "분석 유형. "
                        "summary=전체 요약 중심, "
                        "qa=Q&A 중심, "
                        "keywords=키워드 중심, "
                        "full=모든 항목 포함 (기본값)."
                    ),
                    "default": "full",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


_SCHEMA = {
    "name": "doc_report",
    "schema": {
        "type": "object",
        "properties": {
            "document_title": {"type": "string"},
            "overall_summary": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "summary", "key_points"],
                    "additionalProperties": False,
                },
            },
            "keywords": {"type": "array", "items": {"type": "string"}},
            "qa_pairs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "required": ["question", "answer"],
                    "additionalProperties": False,
                },
            },
            "references": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "document_title",
            "overall_summary",
            "sections",
            "keywords",
            "qa_pairs",
            "references",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}


def _build_user_prompt(args: dict) -> str:
    document_content = (args.get("document_content") or "").strip()
    context_summary = (args.get("context_summary") or "").strip()
    query = (args.get("query") or "").strip()
    analysis_type = (args.get("analysis_type") or "full").strip()

    document_block = (
        f"\n[분석 대상 문서]\n{document_content}\n"
        if document_content
        else "\n[분석 대상 문서]\n(업로드된 문서 없음 — 검색 결과 및 사용자 질의를 기반으로 분석)\n"
    )
    context_block = (
        f"\n[보강 컨텍스트 (RAG/웹 검색)]\n{context_summary}\n"
        if context_summary
        else ""
    )
    type_instruction = {
        "summary": "전체 요약(overall_summary)과 섹션 요약에 집중하세요. qa_pairs는 최소한으로.",
        "qa": "Q&A 쌍(qa_pairs) 생성에 집중하세요. 최소 5개 이상의 Q&A를 작성하세요.",
        "keywords": "키워드(keywords) 추출과 섹션 핵심 포인트에 집중하세요.",
        "full": "요약, 섹션 분석, 키워드, Q&A를 모두 균형 있게 작성하세요.",
    }.get(analysis_type, "요약, 섹션 분석, 키워드, Q&A를 모두 균형 있게 작성하세요.")

    return (
        f"[사용자 요청]\n{query}\n"
        f"{document_block}"
        f"{context_block}\n"
        f"[분석 지시]\n{type_instruction}\n\n"
        "규칙:\n"
        "- 모든 텍스트는 한국어로 작성.\n"
        "- document_title은 문서에서 추정 또는 추출.\n"
        "- overall_summary는 3~5문장으로 핵심만 서술.\n"
        "- sections는 문서의 주요 섹션 또는 주제별로 구분.\n"
        "- key_points는 각 섹션당 2~5개의 불릿 포인트.\n"
        "- keywords는 10~20개의 핵심 기술 용어.\n"
        "- qa_pairs는 문서 내용에 기반한 실질적인 Q&A.\n"
        "- references에는 RAG/웹 검색에서 활용한 출처를 명시. 업로드 문서가 있으면 '업로드 문서' 포함.\n"
    )


def run_analyze_document(arguments: dict) -> str:
    try:
        resp = _client().chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 기술문서 분석 전문가입니다. "
                        "주어진 문서를 정확히 파악하고 구조화된 분석 리포트를 한국어로 생성하세요. "
                        "문서에 없는 내용은 추측하지 말고, 불명확한 경우 솔직히 표시하세요."
                    ),
                },
                {"role": "user", "content": _build_user_prompt(arguments)},
            ],
            temperature=0.2,
            response_format={"type": "json_schema", "json_schema": _SCHEMA},
        )
    except Exception as exc:
        return json.dumps({"error": f"analysis failed: {exc}"}, ensure_ascii=False)

    raw = resp.choices[0].message.content or "{}"
    try:
        report = DocReport.model_validate_json(raw)
    except ValidationError as exc:
        return json.dumps(
            {"error": "schema validation failed", "details": exc.errors(), "raw": raw},
            ensure_ascii=False,
        )
    return report.model_dump_json()
