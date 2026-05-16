"""Streamlit UI for the SingleAgent curriculum backend.

Wired to the FastAPI /chat single endpoint — the backend agent decides
which tools to call, so the UI just orchestrates auth + chat flow.
"""
from __future__ import annotations

import io
import os
from typing import Any

import httpx
import streamlit as st

try:
    import pdfplumber
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

try:
    from docx import Document as DocxDocument
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False

st.set_page_config(page_title="의료기기 기술문서 분석 봇", page_icon="🤖", layout="wide")

# Black & white theme reused from 03_Advanced_RAG.
st.markdown(
    """
<style>
.stApp { background-color: #FFFFFF !important; color: #000000 !important; }
[data-testid="stSidebar"] { background-color: #F8F9FA !important; border-right: 1px solid #E0E0E0 !important; }
h1,h2,h3,h4,h5,h6 { color: #000000 !important; }
.stButton > button { background-color:#000;color:#FFF;border-radius:4px;border:none; }
.stButton > button:hover { background-color:#333;color:#FFF; }
[data-testid="stChatInput"] { border:2px solid #000 !important; border-radius:8px !important; background-color:#FFF !important; }
table { width:100%; border-collapse:collapse; margin:1.5rem 0; }
th { background:#000 !important; color:#FFF !important; padding:12px; border:1px solid #000; text-align:left; }
td { padding:12px; border:1px solid #E0E0E0; color:#000 !important; }
tr:nth-child(even) { background-color:#F9F9F9; }
.trace-pill { display:inline-block; padding:2px 8px; margin:2px; border-radius:999px; background:#111; color:#FFF; font-size:0.75rem; }
.validation-pass { color:#0a6; font-weight:600; }
.validation-fail { color:#c00; font-weight:600; }
</style>
""",
    unsafe_allow_html=True,
)


def get_backend_url() -> str:
    try:
        if "BACKEND_URL" in st.secrets:
            return st.secrets["BACKEND_URL"]
    except Exception:
        pass
    return os.getenv("BACKEND_URL", "https://www.med-ai-chat.streamlit.app")


BACKEND_URL = get_backend_url()


# ── Session state ────────────────────────────────────────────────────────────
def _init_state() -> None:
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("username", None)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("last_doc_report", None)
    st.session_state.setdefault("last_trace", [])
    st.session_state.setdefault("uploaded_document", None)
    st.session_state.setdefault("uploaded_filename", None)


_init_state()


# ── HTTP helpers ─────────────────────────────────────────────────────────────
def _post(path: str, json_body: dict, auth: bool = False) -> tuple[int, Any]:
    headers = {}
    if auth and st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(f"{BACKEND_URL}{path}", json=json_body, headers=headers)
            return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
    except httpx.HTTPError as exc:
        return -1, {"detail": str(exc)}


def _get(path: str, auth: bool = False) -> tuple[int, Any]:
    headers = {}
    if auth and st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{BACKEND_URL}{path}", headers=headers)
            return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
    except httpx.HTTPError as exc:
        return -1, {"detail": str(exc)}


# ── Login view ───────────────────────────────────────────────────────────────
def render_login() -> None:
    st.title("🤖 SingleAgent 기술문서 분석 봇")
    st.caption(f"Backend: `{BACKEND_URL}`")
    with st.form("login_form"):
        u = st.text_input("아이디")
        p = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인", use_container_width=True)
    if submitted:
        code, data = _post("/auth/login", {"username": u, "password": p})
        if code == 200 and isinstance(data, dict) and data.get("access_token"):
            st.session_state.token = data["access_token"]
            st.session_state.username = u
            st.success("로그인 성공")
            st.rerun()
        else:
            detail = data.get("detail") if isinstance(data, dict) else data
            st.error(f"로그인 실패: {detail}")


# ── Chat view ────────────────────────────────────────────────────────────────
def _render_trace() -> None:
    trace = st.session_state.last_trace or []
    if not trace:
        st.info("아직 도구 호출 기록이 없습니다.")
        return
    for i, t in enumerate(trace, 1):
        with st.expander(f"#{i} `{t['name']}`", expanded=False):
            st.json(t.get("arguments") or {})
            preview = t.get("result_preview")
            if preview:
                st.code(preview, language="text")


def _render_doc_report() -> None:
    report = st.session_state.last_doc_report
    if not report:
        st.caption("아직 생성된 분석 리포트가 없습니다.")
        return
    
    st.markdown(f"### 📑 {report['document_title']}")
    st.markdown(f"**전체 요약**")
    st.info(report['overall_summary'])

    if report.get('sections'):
        st.markdown("#### 🔍 섹션별 분석")
        for s in report['sections']:
            with st.expander(f"📌 {s['title']}", expanded=True):
                st.write(s['summary'])
                if s.get('key_points'):
                    st.markdown("\n".join([f"- {p}" for p in s['key_points']]))

    if report.get('qa_pairs'):
        st.markdown("#### ❓ Q&A")
        for qa in report['qa_pairs']:
            st.markdown(f"**Q: {qa['question']}**")
            st.markdown(f"A: {qa['answer']}")
            st.divider()

    if report.get('keywords'):
        st.markdown("#### 🏷️ 핵심 키워드")
        st.write(", ".join(report['keywords']))

    refs = report.get("references") or []
    if refs:
        st.markdown(f"**참고 자료**: {', '.join(refs)}")


def _extract_text(file) -> str:
    """업로드된 파일에서 텍스트를 추출한다."""
    name = file.name.lower()
    if name.endswith(".pdf"):
        if _PDF_AVAILABLE:
            with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            return "\n".join(pages)
        else:
            return file.read().decode("utf-8", errors="ignore")
    elif name.endswith(".docx"):
        if _DOCX_AVAILABLE:
            doc = DocxDocument(io.BytesIO(file.read()))
            return "\n".join(p.text for p in doc.paragraphs)
        else:
            return file.read().decode("utf-8", errors="ignore")
    else:
        return file.read().decode("utf-8", errors="ignore")


def render_chat() -> None:
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.username}**")
        st.caption(f"Backend: `{BACKEND_URL}`")
        if st.button("로그아웃", use_container_width=True):
            for k in ("token", "username", "messages", "last_doc_report", "last_trace", "uploaded_document", "uploaded_filename"):
                st.session_state[k] = None if k in ("token", "username", "last_doc_report", "uploaded_document", "uploaded_filename") else []
            st.rerun()
        st.divider()

        # ── 문서 업로드 ──────────────────────────────────────────────
        st.subheader("📄 참고 문서 업로드")
        uploaded_file = st.file_uploader(
            "TXT / PDF / DOCX 파일을 업로드하세요",
            type=["txt", "pdf", "docx"],
            key="doc_uploader",
            help="업로드한 문서는 기술문서 분석 및 요약 시 최우선 참고 자료로 활용됩니다.",
        )
        if uploaded_file is not None:
            if uploaded_file.name != st.session_state.uploaded_filename:
                with st.spinner("문서 텍스트 추출 중..."):
                    text = _extract_text(uploaded_file)
                st.session_state.uploaded_document = text
                st.session_state.uploaded_filename = uploaded_file.name
                st.success(f"✅ **{uploaded_file.name}** 업로드 완료 ({len(text):,}자)")
        else:
            if st.session_state.uploaded_filename is not None:
                st.session_state.uploaded_document = None
                st.session_state.uploaded_filename = None

        if st.session_state.uploaded_filename:
            st.info(
                f"📎 현재 문서: **{st.session_state.uploaded_filename}**  \n"
                f"({len(st.session_state.uploaded_document or ''):,}자)"
            )
            if st.button("문서 제거", use_container_width=True):
                st.session_state.uploaded_document = None
                st.session_state.uploaded_filename = None
                st.rerun()

        st.divider()
        st.subheader("최근 도구 호출")
        _render_trace()

    st.title("🤖 SingleAgent 기술문서 분석 봇")
    st.caption("단일 에이전트가 기술문서를 분석하고 요약합니다. (RAG · 웹 검색 · 분석 툴 활용)")

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("💬 대화")
        chat_box = st.container(height=520)
        with chat_box:
            for m in st.session_state.messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

        if prompt := st.chat_input("문서 분석 요청 또는 질문을 입력하세요"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with chat_box:
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    placeholder = st.empty()
                    placeholder.markdown("⏳ 에이전트가 작업 중...")
                    code, data = _post(
                        "/chat",
                        {
                            "message": prompt,
                            "history": [
                                {"role": m["role"], "content": m["content"]}
                                for m in st.session_state.messages[:-1]
                            ],
                            "uploaded_document": st.session_state.get("uploaded_document"),
                        },
                        auth=True,
                    )
                    if code == 200 and isinstance(data, dict):
                        reply = data.get("reply") or "(빈 응답)"
                        placeholder.markdown(reply)
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                        st.session_state.last_doc_report = data.get("doc_report")
                        st.session_state.last_trace = data.get("tool_trace") or []
                        if not data.get("complete"):
                            st.warning("분석이 완료되지 않았습니다.")
                    elif code == 401:
                        st.error("인증 만료 — 다시 로그인 해 주세요.")
                        st.session_state.token = None
                    else:
                        detail = data.get("detail") if isinstance(data, dict) else data
                        placeholder.error(f"오류: {detail}")
                        st.session_state.messages.append(
                            {"role": "assistant", "content": f"❌ 오류: {detail}"}
                        )
            st.rerun()

    with right:
        st.subheader("📋 최근 분석 리포트")
        _render_doc_report()


# ── Auth gate ────────────────────────────────────────────────────────────────
def _token_valid() -> bool:
    if not st.session_state.token:
        return False
    code, _ = _get("/auth/verify", auth=True)
    return code == 200


if not _token_valid():
    render_login()
else:
    render_chat()
