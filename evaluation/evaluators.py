import json
import re
from typing import Any, List
from openai import OpenAI
from backend.app.config import settings
from backend.app.schemas.curriculum import DocReport
from .schemas import TestCase, EvaluationResult

class BaseEvaluator:
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)

    def _ask_llm(self, prompt: str) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=settings.chat_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Error: {e}"

class RetrievalEvaluator:
    def evaluate(self, retrieved_hits: List[dict], expected_ids: List[str]) -> float:
        if not expected_ids:
            return 1.0  # 정답셋이 없으면 평가 제외 (통과 처리)
        
        retrieved_sources = [hit.get("source", "") for hit in retrieved_hits]
        match_count = 0
        for eid in expected_ids:
            if any(eid in src for src in retrieved_sources):
                match_count += 1
        
        return match_count / len(expected_ids)

class FaithfulnessEvaluator(BaseEvaluator):
    def evaluate(self, query: str, context: str, reply: str) -> tuple[float, str]:
        prompt = f"""
[Task] 생성된 답변이 제공된 검색 근거(Context)에 충실한지 평가하세요.
[Context]
{context}

[Generated Reply]
{reply}

[Rules]
1. 답변의 모든 내용이 Context에 기반하고 있다면 1.0점.
2. Context에 없는 내용이 포함되어 있거나 사실 왜곡이 있다면 감점.
3. 근거가 전혀 없다면 0.0점.

결과 형식 (점수와 이유를 JSON으로):
{{"score": 0.0~1.0, "reason": "이유 설명"}}
"""
        res = self._ask_llm(prompt)
        try:
            data = json.loads(re.search(r"\{.*\}", res, re.DOTALL).group())
            return float(data.get("score", 0)), data.get("reason", "")
        except:
            return 0.0, "JSON Parsing Failed"

class RequirementCoverageEvaluator(BaseEvaluator):
    def evaluate(self, requirements: List[str], reply: str) -> tuple[float, str]:
        if not requirements:
            return 1.0, "No requirements defined"
            
        req_list = "\n".join([f"- {r}" for r in requirements])
        prompt = f"""
[Task] 사용자의 요구사항이 답변에 얼마나 반영되었는지 평가하세요.
[Requirements]
{req_list}

[Generated Reply]
{reply}

[Rules]
1. 각 요구사항이 명확히 반영되었는지 확인.
2. 반영된 비율만큼 점수 부여 (모두 반영 시 1.0).

결과 형식 (점수와 이유를 JSON으로):
{{"score": 0.0~1.0, "reason": "이유 설명"}}
"""
        res = self._ask_llm(prompt)
        try:
            data = json.loads(re.search(r"\{.*\}", res, re.DOTALL).group())
            return float(data.get("score", 0)), data.get("reason", "")
        except:
            return 0.0, "JSON Parsing Failed"

class RuleEvaluator:
    def evaluate(self, doc_report: DocReport | None) -> tuple[float, list[str]]:
        if not doc_report:
            return 0.0, ["DocReport is missing"]
            
        issues = []
        score = 1.0
        
        # Rule 1: 전체 요약 길이 (최소 50자)
        if len(doc_report.overall_summary) < 50:
            issues.append("Overall summary is too short (< 50 chars)")
            score -= 0.2
            
        # Rule 2: 섹션 개수 (최소 2개)
        if len(doc_report.sections) < 2:
            issues.append("Too few sections (< 2)")
            score -= 0.2
            
        # Rule 3: 키워드 개수 (최소 5개)
        if len(doc_report.keywords) < 5:
            issues.append("Too few keywords (< 5)")
            score -= 0.2
            
        # Rule 4: Q&A 개수 (최소 2개)
        if len(doc_report.qa_pairs) < 2:
            issues.append("Too few QA pairs (< 2)")
            score -= 0.2
            
        # Rule 5: 출처 명시
        if not doc_report.references:
            issues.append("No references cited")
            score -= 0.2

        return max(0.0, score), issues
