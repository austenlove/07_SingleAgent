"""Streamlit UI for SingleAgent - Integrated Version (Monolith).

This version calls the agent logic directly instead of using a separate FastAPI backend.
Ideal for simpler deployments like Streamlit Cloud.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import Any

# 프로젝트 루트를 경로에 추가하여 backend 패키지를 읽을 수 있게 함
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

import streamlit as st
from dotenv import load_dotenv

# 에이전트 및 설정 직접 임포트
from backend.app.agent import run_agent
from backend.app.config import settings
from backend.app.schemas.chat import ChatMessage

# .env 로드 (로컬 개발용)
load_dotenv()

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

# Black & white theme
st.markdown(
    """
<style>
.stApp { background-color: #FFFFFF !important; color: #000000 !important; }
[data-testid="stSidebar"] { background-color: #F8F9FA !important; border-right: 1px solid #E0E0E0 !important; }
/* 모든 텍스트 요소를 검은색으로 강제 (배포 환경 다크모드 이슈 방지) */
h1, h2, h3, h4, h5, h6, p, li, span, label, div { color: #000000 !important; }
.stButton > button { background-color:#000;color:#FFF;border-radius:4px;border:none; width: 100%; }
.stButton > button:hover { background-color:#333;color:#FFF; }
[data-testid="stChatInput"] { border:2px solid #000 !important; border-radius:8px !important; background-color:#FFF !important; }
table { width:100%; border-collapse:collapse; margin:1.5rem 0; }
th { background:#000 !important; color:#FFF !important; padding:12px; border:1px solid #000; text-align:left; }
td { padding:12px; border:1px solid #E0E0E0; color:#000 !important; }
tr:nth-child(even) { background-color:#F9F9F9; }
/* 사이드바 내부 텍스트 색상 별도 지정 */
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span { color: #000000 !important; }
</style>
""",
    unsafe_allow_html=True,
)

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

# ── Login view ───────────────────────────────────────────────────────────────
def render_login() -> None:
    # 화면 중앙에 배치하기 위해 컬럼 사용
    _, col, _ = st.columns([1, 1.2, 1])
    
    with col:
        st.write("") # 상단 여백
        st.write("")
        st.title("🤖 의료기기 기술문서 분석 봇")
        st.caption("단일 에이전트가 기술문서를 분석하고 요약합니다. (통합형)")
        
        with st.form("login_form"):
            u = st.text_input("아이디")
            p = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인", use_container_width=True)
        
        if submitted:
            if u == settings.admin_username and p == settings.admin_password:
                st.session_state.token = "integrated-session"
                st.session_state.username = u
                st.success("로그인 성공")
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

# ── Chat view ────────────────────────────────────────────────────────────────
def _render_trace() -> None:
    trace = st.session_state.last_trace or []
    if not trace:
        st.info("아직 도구 호출 기록이 없습니다.")
        return
    for i, t in enumerate(trace, 1):
        # t is ToolTrace object or dict
        t_data = t.model_dump() if hasattr(t, "model_dump") else t
        with st.expander(f"#{i} `{t_data['name']}`", expanded=False):
            st.json(t_data.get("arguments") or {})
            preview = t_data.get("result_preview")
            if preview:
                st.code(preview, language="text")

def _render_doc_report() -> None:
    report = st.session_state.last_doc_report
    if not report:
        st.caption("아직 생성된 분석 리포트가 없습니다.")
        return
    
    # report is DocReport object or dict
    r = report.model_dump() if hasattr(report, "model_dump") else report
    
    st.markdown(f"### 📑 {r['document_title']}")
    st.markdown(f"**전체 요약**")
    st.info(r['overall_summary'])

    if r.get('sections'):
        st.markdown("#### 🔍 섹션별 분석")
        for s in r['sections']:
            with st.expander(f"📌 {s['title']}", expanded=True):
                st.write(s['summary'])
                if s.get('key_points'):
                    st.markdown("\n".join([f"- {p}" for p in s['key_points']]))

    if r.get('qa_pairs'):
        st.markdown("#### ❓ Q&A")
        for qa in r['qa_pairs']:
            st.markdown(f"**Q: {qa['question']}**")
            st.markdown(f"A: {qa['answer']}")
            st.divider()

    if r.get('keywords'):
        st.markdown("#### 🏷️ 핵심 키워드")
        st.write(", ".join(r['keywords']))

    refs = r.get("references") or []
    if refs:
        st.markdown(f"**참고 자료**: {', '.join(refs)}")

def _extract_text(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf") and _PDF_AVAILABLE:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            return "\n".join([page.extract_text() or "" for page in pdf.pages])
    elif name.endswith(".docx") and _DOCX_AVAILABLE:
        doc = DocxDocument(io.BytesIO(file.read()))
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        return file.read().decode("utf-8", errors="ignore")

def render_chat() -> None:
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.username}**")
        if st.button("로그아웃", use_container_width=True):
            # 모든 세션 상태 초기화
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        st.divider()

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
                st.success(f"✅ **{uploaded_file.name}** 업로드 완료")
                
                # 자동 요약 요청 생성
                with st.spinner("문서 요약 생성 중..."):
                    summary_prompt = f"새로운 문서 '{uploaded_file.name}'가 업로드되었습니다. 이 문서의 주요 구성과 핵심 내용을 표(Table) 형태로 요약해서 설명해줘."
                    response = run_agent(
                        user_message=summary_prompt,
                        history=[ChatMessage(**m) for m in st.session_state.messages],
                        uploaded_document=text
                    )
                    st.session_state.messages.append({"role": "user", "content": f"📎 문서 업로드: {uploaded_file.name}"})
                    st.session_state.messages.append({"role": "assistant", "content": response.reply})
                    st.session_state.last_doc_report = response.doc_report
                    st.session_state.last_trace = response.tool_trace
                st.rerun()
            st.session_state.uploaded_document = None
            st.session_state.uploaded_filename = None

        if st.session_state.uploaded_filename:
            st.info(f"📎 현재 문서: **{st.session_state.uploaded_filename}**")
            if st.button("문서 제거", use_container_width=True):
                st.session_state.uploaded_document = None
                st.session_state.uploaded_filename = None
                st.rerun()

        st.divider()
        st.subheader("최근 도구 호출")
        _render_trace()

    st.title("🤖 의료기기 기술문서 분석 봇")
    st.caption("단일 에이전트가 기술문서를 분석하고 요약합니다. (통합형)")

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
                    with st.spinner("에이전트가 작업 중..."):
                        # 에이전트 직접 호출 (API 호출 없음)
                        history_objs = [ChatMessage(**m) for m in st.session_state.messages[:-1]]
                        try:
                            response = run_agent(
                                user_message=prompt,
                                history=history_objs,
                                uploaded_document=st.session_state.get("uploaded_document")
                            )
                            reply = response.reply
                            st.markdown(reply)
                            st.session_state.messages.append({"role": "assistant", "content": reply})
                            st.session_state.last_doc_report = response.doc_report
                            st.session_state.last_trace = response.tool_trace
                            
                            if not response.complete:
                                st.warning("분석이 완료되지 않았습니다.")
                        except Exception as e:
                            err_msg = f"에이전트 실행 중 오류가 발생했습니다: {e}"
                            st.error(err_msg)
                            st.session_state.messages.append({"role": "assistant", "content": f"❌ {err_msg}"})
            st.rerun()

    with right:
        st.subheader("📋 최근 분석 리포트")
        _render_doc_report()

# ── Auth gate ────────────────────────────────────────────────────────────────
if not st.session_state.token:
    render_login()
else:
    render_chat()
