# 07_SingleAgent RAG 평가 모듈

이 모듈은 기술문서 분석 에이전트의 성능을 정량적으로 측정하기 위한 평가 파이프라인입니다.

## 1. 주요 평가 항목

- **Retrieval 평가 (Precision@k)**: 에이전트가 `rag_search`를 통해 정답 문서(`expected_doc_ids`)를 얼마나 정확하게 찾아냈는지 측정합니다.
- **Faithfulness 평가 (Groundedness)**: 생성된 답변이 검색된 근거(Context) 내에 존재하는 정보인지 LLM(GPT-4o 등)을 통해 검증합니다.
- **Requirement Coverage 평가**: 사용자의 구체적인 요구사항(`requirements`)이 답변에 얼마나 반영되었는지 측정합니다.
- **Rule 기반 평가**: 분석 결과 구조(`DocReport`)가 다음 규칙을 준수하는지 확인합니다.
  - 전체 요약 길이 (50자 이상)
  - 섹션 개수 (2개 이상)
  - 키워드 및 Q&A 개수
  - 출처 표기 여부

## 2. 사용 방법

### (1) 테스트셋 구성
`evaluation/test_cases.json` 파일을 수정하여 평가하려는 시나리오를 추가합니다.

```json
{
  "id": "TC-001",
  "query": "질문 내용",
  "expected_doc_ids": ["기대_파일명.pdf"],
  "requirements": ["반드시 포함될 내용 1", "내용 2"]
}
```

### (2) 평가 실행
프로젝트 루트 디렉토리에서 다음 명령을 실행합니다.

```bash
python -m evaluation.runner
```

### (3) 결과 확인
실행이 완료되면 `evaluation/reports/` 디렉토리에 타임스탬프가 포함된 결과 파일이 생성됩니다.
- `report_YYYYMMDD_HHMMSS.json`: 상세 데이터가 포함된 원본 리포트
- `report_YYYYMMDD_HHMMSS.md`: 한눈에 볼 수 있는 요약 마크다운 리포트

## 3. 구조

- `schemas.py`: 평가 데이터 및 결과용 Pydantic 모델
- `evaluators.py`: 항목별 평가 로직 (Retrieval, LLM-based, Rule-based)
- `runner.py`: 전체 테스트셋을 순회하며 에이전트를 구동하고 점수를 집계하는 실행기
