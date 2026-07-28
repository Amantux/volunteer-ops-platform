"""Chat assistant endpoints: a streaming (SSE) chat for signed-in users, and admin-only settings
to configure the per-org provider (Ollama/Anthropic). The assistant is read-only + governed
(see app.modules.agents.assistant); nothing here can send, publish, or move money."""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.authz import Principal
from app.modules.agents import assistant

from .deps import current_principal, get_db, require_permission

router = APIRouter(prefix="/api", tags=["assistant"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    messages: list[ChatMessage]


@router.get("/agent/config")
def agent_config(db: Session = Depends(get_db),
                 principal: Principal = Depends(current_principal)):
    cfg = assistant.resolve_config(db, principal.org_id)
    return {"enabled": cfg.enabled, "provider": cfg.provider, "model": cfg.model}


@router.post("/agent/chat")
def agent_chat(payload: ChatIn, request: Request, db: Session = Depends(get_db),
               principal: Principal = Depends(current_principal)):
    if not ratelimit.allow(f"assistant:{principal.user_id}", limit=30, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many messages — slow down a moment.")
    messages = [m.model_dump() for m in payload.messages]

    def _events():
        for ev in assistant.stream_chat(db, principal, messages):
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- Admin configuration --------------------------------------------------------------- #

def _safe_base_url(url: str) -> bool:
    """Allow http(s) to loopback/LAN (where Ollama runs) but block link-local/metadata targets —
    the base URL is admin-supplied and used server-side (SSRF guard)."""
    if not url:
        return True  # empty = fall back to env default
    if not url.startswith(("http://", "https://")):
        return False
    host = urllib.parse.urlparse(url).hostname
    if not host:
        return False
    try:
        for res in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(res[4][0])
            if ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False  # block metadata/link-local (e.g. 169.254.169.254)
    except OSError:
        # Unresolvable now (e.g. host.docker.internal outside Docker) — can't be a metadata target;
        # admin-supplied and validated again at call time. Allow (semi-trusted admin stance).
        return True
    return True


class AgentSettingsIn(BaseModel):
    provider: str | None = None       # off | ollama | anthropic
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None        # blank on save = keep existing
    system_prompt: str | None = None
    timeout: int | None = None
    max_steps: int | None = None


@router.get("/admin/agent-settings")
def get_agent_settings(db: Session = Depends(get_db),
                       principal: Principal = Depends(require_permission("assistant.configure"))):
    return assistant.public_config(assistant.resolve_config(db, principal.org_id))


@router.put("/admin/agent-settings")
def put_agent_settings(payload: AgentSettingsIn, db: Session = Depends(get_db),
                       principal: Principal = Depends(require_permission("assistant.configure"))):
    patch = payload.model_dump(exclude_none=True)
    if "provider" in patch and patch["provider"] not in ("off", "ollama", "anthropic"):
        raise HTTPException(status_code=400, detail="invalid provider")
    if "base_url" in patch and not _safe_base_url(patch["base_url"]):
        raise HTTPException(status_code=400, detail="base_url must be http(s) to a permitted host")
    assistant.set_org_config(db, principal.org_id, patch)
    db.commit()
    return assistant.public_config(assistant.resolve_config(db, principal.org_id))


@router.post("/admin/agent-settings/models")
def list_models(db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("assistant.configure"))):
    """Probe the configured provider for its installed models (populates the admin dropdown)."""
    cfg = assistant.resolve_config(db, principal.org_id)
    if cfg.provider == "ollama" and cfg.base_url:
        if not _safe_base_url(cfg.base_url):
            raise HTTPException(status_code=400, detail="base_url not permitted")
        try:
            req = urllib.request.Request(cfg.base_url.rstrip("/") + "/api/tags")
            with urllib.request.urlopen(req, timeout=cfg.timeout) as r:  # noqa: S310  # nosec B310
                data = json.loads(r.read().decode())
            return {"models": [m.get("name") for m in data.get("models", [])]}
        except Exception as exc:  # noqa: BLE001 - surface a friendly error to the settings UI
            raise HTTPException(status_code=502, detail=f"could not reach Ollama: {exc}") from exc
    return {"models": []}
