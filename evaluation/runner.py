import json
import os
import sys
from datetime import datetime
from typing import List

# 프로젝트 루트를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.agent import run_agent
from evaluation.schemas import TestCase, EvaluationResult, AggregateReport
from evaluation.evaluators import (
    RetrievalEvaluator,
    FaithfulnessEvaluator,
    RequirementCoverageEvaluator,
    RuleEvaluator
)

class EvaluationRunner:
    def __init__(self):
        self.retrieval_eval = RetrievalEvaluator()
        self.faith_eval = FaithfulnessEvaluator()
        self.coverage_eval = RequirementCoverageEvaluator()
        self.rule_eval = RuleEvaluator()

    def run(self, test_cases_path: str):
        with open(test_cases_path, "r", encoding="utf-8") as f:
            cases_data = json.load(f)
            test_cases = [TestCase(**c) for c in cases_data]

        results = []
        for case in test_cases:
            print(f"[{case.id}] Running agent for: {case.query}")
            
            # 1. Agent 실행
            response = run_agent(case.query, history=[])
            
            # 2. 검색 근거 추출 (trace에서)
            retrieved_hits = []
            context_text = ""
            for trace in response.tool_trace:
                if trace.name == "rag_search":
                    # 실제 툴 결과(JSON 문자열)를 파싱해야 함
                    try:
                        res_data = json.loads(trace.result_preview if "{" in trace.result_preview else "{}")
                        hits = res_data.get("results", [])
                        retrieved_hits.extend(hits)
                        context_text += "\n".join([h.get("text", "") for h in hits])
                    except:
                        pass
            
            # 3. 평가
            # Retrieval
            p_score = self.retrieval_eval.evaluate(retrieved_hits, case.expected_doc_ids)
            
            # Faithfulness
            f_score, f_reason = self.faith_eval.evaluate(case.query, context_text, response.reply)
            
            # Requirement Coverage
            c_score, c_reason = self.coverage_eval.evaluate(case.requirements, response.reply)
            
            # Rules
            r_score, r_issues = self.rule_eval.evaluate(response.doc_report)
            
            total_score = (p_score + f_score + c_score + r_score) / 4.0
            
            res = EvaluationResult(
                test_case_id=case.id,
                query=case.query,
                retrieval_precision=p_score,
                retrieved_sources=[h.get("source", "unknown") for h in retrieved_hits],
                faithfulness_score=f_score,
                faithfulness_reason=f_reason,
                requirement_coverage_score=c_score,
                requirement_coverage_reason=c_reason,
                rule_score=r_score,
                rule_details=r_issues,
                total_score=total_score,
                generated_reply=response.reply,
                has_doc_report=response.doc_report is not None
            )
            results.append(res)
            print(f"  -> Score: {total_score:.2f}")

        # 4. 리포트 생성
        report = self.generate_aggregate_report(results)
        self.save_reports(report)

    def generate_aggregate_report(self, results: List[EvaluationResult]) -> AggregateReport:
        n = len(results)
        if n == 0:
            return AggregateReport(total_cases=0, avg_precision=0, avg_faithfulness=0, avg_coverage=0, avg_rule_score=0, avg_total_score=0, results=[])
            
        return AggregateReport(
            total_cases=n,
            avg_precision=sum(r.retrieval_precision for r in results) / n,
            avg_faithfulness=sum(r.faithfulness_score for r in results) / n,
            avg_coverage=sum(r.requirement_coverage_score for r in results) / n,
            avg_rule_score=sum(r.rule_score for r in results) / n,
            avg_total_score=sum(r.total_score for r in results) / n,
            results=results
        )

    def save_reports(self, report: AggregateReport):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("evaluation/reports", exist_ok=True)
        
        # JSON Report
        json_path = f"evaluation/reports/report_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
            
        # Markdown Report
        md_path = f"evaluation/reports/report_{timestamp}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# RAG Evaluation Report ({timestamp})\n\n")
            f.write("## 1. Summary Scores\n")
            f.write(f"- Total Cases: {report.total_cases}\n")
            f.write(f"- Avg Total Score: **{report.avg_total_score:.2f}**\n")
            f.write(f"  - Retrieval Precision: {report.avg_precision:.2f}\n")
            f.write(f"  - Faithfulness: {report.avg_faithfulness:.2f}\n")
            f.write(f"  - Requirement Coverage: {report.avg_coverage:.2f}\n")
            f.write(f"  - Rule Satisfaction: {report.avg_rule_score:.2f}\n\n")
            
            f.write("## 2. Detailed Results\n")
            for r in report.results:
                f.write(f"### [{r.test_case_id}] {r.query}\n")
                f.write(f"- **Score**: {r.total_score:.2f}\n")
                f.write(f"- **Retrieval**: {r.retrieval_precision:.2f} ({', '.join(r.retrieved_sources[:3])}...)\n")
                f.write(f"- **Faithfulness**: {r.faithfulness_score:.2f} ({r.faithfulness_reason})\n")
                f.write(f"- **Coverage**: {r.requirement_coverage_score:.2f} ({r.requirement_coverage_reason})\n")
                f.write(f"- **Rules**: {r.rule_score:.2f} ({', '.join(r.rule_details)})\n")
                f.write(f"- **DocReport Generated**: {'✅' if r.has_doc_report else '❌'}\n\n")

        print(f"\n[Done] Reports saved to evaluation/reports/")
        print(f"  - JSON: {json_path}")
        print(f"  - Markdown: {md_path}")

if __name__ == "__main__":
    runner = EvaluationRunner()
    path = "evaluation/test_cases.json"
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
    else:
        runner.run(path)
