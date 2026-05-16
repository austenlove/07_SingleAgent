"""FastAPI entrypoint for the 07_SingleAgent backend.

Endpoints
---------
- POST /auth/login    issue JWT
- GET  /auth/verify   validate JWT
- GET  /health        liveness + dependency probe
- POST /chat          run the single agent (auth required)
"""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .agent import run_agent
from .auth import (
    create_access_token,
    require_user,
    verify_credentials,
)
from .config import settings
from .schemas import (
    ChatRequest,
    ChatResponse,
    LoginRequest,
    TokenResponse,
    VerifyResponse,
)

logger = logging.getLogger("singleagent")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="SingleAgent Curriculum Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "max_agent_steps": settings.max_agent_steps,
        "agent_type": "technical_doc_analyzer",
    }


@app.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    if not verify_credentials(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token, exp = create_access_token(body.username)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
    )


@app.get("/auth/verify", response_model=VerifyResponse)
def verify(user: str = Depends(require_user)) -> VerifyResponse:
    return VerifyResponse(valid=True, username=user)


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: str = Depends(require_user)) -> ChatResponse:
    logger.info("chat request user=%s len=%d", user, len(body.message))
    try:
        return run_agent(body.message, body.history, body.uploaded_document)
    except Exception as exc:  # noqa: BLE001 — surface to client for ops debugging
        logger.exception("agent loop failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"agent error: {exc}",
        ) from exc
