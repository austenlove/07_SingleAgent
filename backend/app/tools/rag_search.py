"""내부 RAG 검색 툴 — 기술문서 지식베이스에서 관련 정보를 검색한다."""
from __future__ import annotations

import json

from ..retriever import hybrid_search

RAG_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "rag_search",
        "description": (
            "내부 지식베이스에서 사용자의 질의와 관련된 기술문서를 "
            "하이브리드 검색(Dense + BM25 + Rerank)으로 찾는다. "
            "업로드된 문서 외에 추가 배경 지식이나 관련 기술 정보를 보강할 때 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "한국어 자연어 검색 질의. 핵심 기술 키워드를 포함시킬 것.",
                },
                "k": {
                    "type": "integer",
                    "description": "반환할 결과 수 (1~8). 기본 5.",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 5,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def run_rag_search(arguments: dict) -> str:
    query = (arguments.get("query") or "").strip()
    k = int(arguments.get("k") or 5)
    if not query:
        return json.dumps({"error": "query is required"}, ensure_ascii=False)

    hits = hybrid_search(query, k=k)
    if not hits:
        return json.dumps(
            {"query": query, "results": [], "note": "no matching documents"},
            ensure_ascii=False,
        )

    results = []
    for h in hits:
        meta = h.get("meta") or {}
        results.append(
            {
                "source": meta.get("source", "unknown"),
                "page": meta.get("page_number"),
                "text": h["text"][:1200],
            }
        )
    return json.dumps({"query": query, "results": results}, ensure_ascii=False)
