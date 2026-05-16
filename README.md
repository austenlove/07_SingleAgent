# 07_SingleAgent

`03_Advanced_RAG` 의 고정 파이프라인(chat → generate)을 **단일 Agent (OpenAI tool-calling / ReAct)** 구조로 전환한 프로젝트.
에이전트는 한 번의 사용자 메시지마다 4 개 툴 중 필요한 것을 골라 호출하고, 검증 실패 시 한도 안에서 재생성합니다.

## 구조

```
07_SingleAgent/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI 엔트리포인트 (/health, /auth/*, /chat)
│   │   ├── agent.py           Single Agent 루프 (ReAct + 검증 재시도)
│   │   ├── retriever.py       Dense + BM25 + RRF + Rerank 하이브리드 검색
│   │   ├── auth.py            JWT 발급/검증
│   │   ├── config.py          환경변수 로딩
│   │   ├── tools/             rag_search · web_search · generate_curriculum · validate_curriculum
│   │   └── schemas/           Pydantic 모델 (chat / auth / curriculum)
│   ├── prompts/system_prompt.txt
│   ├── data/                  03_Advanced_RAG 의 chroma_db, bm25_index.pkl 재사용
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── streamlit_app.py       단일 에이전트 대화 UI
│   ├── .streamlit/config.toml
│   └── requirements.txt
├── docker/docker-compose.yml
├── .env.example
└── README.md
```

## API

| Method | Path | 설명 |
| --- | --- | --- |
| GET  | `/health` | 라이브니스 확인 |
| POST | `/auth/login` | `{username, password}` → JWT 발급 |
| GET  | `/auth/verify` | Bearer 토큰 검증 |
| POST | `/chat` | 단일 엔드포인트. `reply / complete / curriculum / validation_result / tool_trace / attempts` 반환 |

### `/chat` 응답 예시

```json
{
  "reply": "...마크다운 표 포함 최종 응답...",
  "complete": true,
  "curriculum": { "topic": "...", "modules": [ ... ] },
  "validation_result": { "passed": true, "issues": [], "summary": "..." },
  "tool_trace": [
    { "name": "rag_search", "arguments": { "query": "..." }, "result_preview": "..." },
    { "name": "generate_curriculum", "arguments": { ... } },
    { "name": "validate_curriculum", "arguments": { ... } }
  ],
  "attempts": 1
}
```

## 단일 에이전트 동작 흐름

1. 사용자 메시지를 받으면 `system_prompt.txt` 기반 ReAct 컨텍스트를 구성.
2. `rag_search` 로 내부 자료를 우선 조회 → 필요 시 `web_search` 로 보강.
3. `generate_curriculum` 으로 JSON 초안 생성 (OpenAI structured output).
4. 곧바로 `validate_curriculum` 으로 시간/구조/그룹 규칙 검증.
5. 실패 시 `feedback` 을 담아 `generate_curriculum` 재호출. 단, `MAX_VALIDATION_RETRIES`(기본 2회) 이후에는 재시도 중단.
6. 전 과정의 단계 수는 `MAX_AGENT_STEPS`(기본 8) 로 무한루프 방지.

## 환경 변수

`.env.example` 참조. 다음 키는 **필수** (없으면 부팅 실패):

- `OPENAI_API_KEY`
- `TAVILY_API_KEY`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`

선택값으로 `JWT_SECRET`, `MAX_AGENT_STEPS`, `MAX_VALIDATION_RETRIES`, `CHAT_MODEL` 등.

## 로컬 실행

```powershell
# 백엔드
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example ..\.env   # 그리고 키 채우기
uvicorn app.main:app --reload --port 8000

# 프론트엔드 (별도 터미널)
cd frontend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:BACKEND_URL = "http://localhost:8000"
streamlit run streamlit_app.py
```

## Docker 백엔드 배포

```powershell
# 프로젝트 루트에서
copy .env.example .env  # 키 채우기

docker compose -f docker/docker-compose.yml up -d --build
# → http://localhost:8000/health
```

원격 배포 시 `8000` 포트를 외부로 열고, 프론트엔드 `BACKEND_URL` 을 해당 URL 로 지정합니다.

## Streamlit Cloud 프론트엔드 배포

1. GitHub repo 에 `frontend/streamlit_app.py` 와 `frontend/requirements.txt` 가 함께 올라가 있어야 합니다.
2. Streamlit Cloud → New app → repo / branch / main file path = `frontend/streamlit_app.py`.
3. **Settings → Secrets** 에 다음을 입력:
   ```toml
   BACKEND_URL = "https://<your-backend-host>"
   ```
4. 배포 후 처음 접속 시 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 로 로그인.

## 03_Advanced_RAG 에서 달라진 점

| 항목 | 03_Advanced_RAG | 07_SingleAgent |
| --- | --- | --- |
| 동작 방식 | Streamlit 안에서 직접 `answer_question` 호출, 검색 → 생성 고정 파이프라인 | FastAPI 백엔드의 ReAct Agent 가 매 호출마다 어떤 툴을 쓸지 스스로 결정 |
| 엔드포인트 | 없음 (Streamlit 일체형) | `/chat` 단일 엔드포인트 + JWT 인증 |
| 검증 | 없음 | `validate_curriculum` 규칙 기반 검증 + 재생성 루프 |
| 프롬프트 | 코드에 인라인 | `backend/prompts/system_prompt.txt` 로 분리 |
| 외부 검색 | 없음 | Tavily `web_search` 툴 |
| 배포 | Streamlit Cloud 단일 | Streamlit Cloud (프론트) + Docker (백엔드) |
