"""External web search tool — Tavily API.

Used when the internal RAG does not have sufficient context (recent trends,
specific company names, fresh statistics, etc.).
"""
from __future__ import annotations

import json

import httpx

from ..config import settings

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Tavily 외부 웹 검색. 내부 RAG에 없는 최신 트렌드·통계·사례를 "
            "보강할 때 호출한다. 일반 상식이나 이미 알고 있는 내용에는 사용하지 말 것."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색어 (한국어 또는 영어)"},
                "max_results": {
                    "type": "integer",
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

_TAVILY_URL = "https://api.tavily.com/search"


def run_web_search(arguments: dict) -> str:
    query = (arguments.get("query") or "").strip()
    max_results = int(arguments.get("max_results") or 5)
    if not query:
        return json.dumps({"error": "query is required"}, ensure_ascii=False)

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": True,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(_TAVILY_URL, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        return json.dumps(
            {"error": f"tavily request failed: {exc}"}, ensure_ascii=False
        )

    results = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "content": (item.get("content") or "")[:800],
        }
        for item in (data.get("results") or [])
    ]
    return json.dumps(
        {
            "query": query,
            "answer": data.get("answer"),
            "results": results,
        },
        ensure_ascii=False,
    )
