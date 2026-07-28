"""Governed chat assistant (Ollama / Anthropic), configurable per-org by admins.

Design mirrors Edibl's assistant: a bounded tool-call loop over a `name -> (schema, handler)`
registry, stateless (the client resends the transcript), with config resolved env-default →
per-org override. Differences enforced here: this platform's assistant is **governed** — v1 tools
are strictly READ-ONLY and permission-gated per caller, so the assistant answers/《FYI》s from the
caller's own authorized data and can never send, publish, refund, or delete. Drafting and
approval-gated proposals are a later, deliberate expansion.

Config (per-org override in OrganizationSetting["assistant"] wins over env defaults):
  provider: "off" | "ollama" | "anthropic"   base_url, model, api_key, system_prompt, timeout,
  max_steps. `enabled` is derived from provider.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.authz import Principal, has_permission
from app.core.config import settings
from app.modules.org.models import OrganizationSetting

# Known cloud metadata endpoints (169.254.169.254 is link-local; 100.100.100.200 is Alibaba and
# is NOT link-local, so deny it explicitly). Loopback/LAN are intentionally allowed (Ollama).
_METADATA_IPS = {"169.254.169.254", "100.100.100.200"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects — otherwise a validated base_url could 302 to cloud metadata."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def is_safe_url(url: str) -> bool:
    """SSRF guard for the admin-supplied LLM base URL: http(s) only, never a metadata/link-local
    target. Loopback/LAN allowed (Ollama). Unresolvable = allowed (can't be a metadata target;
    re-checked at call time). Residual DNS-rebinding is accepted (semi-trusted admin)."""
    if not url:
        return True
    if not url.startswith(("http://", "https://")):
        return False
    host = urllib.parse.urlparse(url).hostname
    if not host:
        return False
    try:
        for res in socket.getaddrinfo(host, None):
            addr = res[4][0]
            if addr in _METADATA_IPS:
                return False
            ip = ipaddress.ip_address(addr)
            if ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
    except OSError:
        return True
    return True


def _guarded_open(req: urllib.request.Request, *, timeout: int):
    """Validate the URL and open it with redirects disabled (SSRF-safe) on every call — not just at
    config-save time."""
    if not is_safe_url(req.full_url):
        raise AssistantError("blocked URL")
    return _OPENER.open(req, timeout=timeout)  # noqa: S310  # nosec B310


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

_SYSTEM_PROMPT = (
    "You are the volunteer-operations assistant for this organization. Help signed-in staff and "
    "volunteers with clear, concise answers about schedules, shifts, training, programs, and "
    "(for finance staff) donations. Prefer calling a tool to look up real data over guessing. "
    "You can READ data the current user is authorized to see, and you can DRAFT content (e.g. a "
    "social post) or PROPOSE an approval-gated action (e.g. promoting a waitlisted volunteer) — "
    "these only create a draft or a request that a human must review and approve. You can NEVER "
    "send messages, publish, move money, or change records directly; if asked, explain that you've "
    "drafted/proposed it and a staff member must approve it in the app. Keep answers short and practical."
)

_ASSISTANT_SETTING_KEY = "assistant"


@dataclass
class AssistantConfig:
    provider: str
    base_url: str
    model: str
    api_key: str
    system_prompt: str
    timeout: int
    max_steps: int

    @property
    def enabled(self) -> bool:
        return self.provider in ("ollama", "anthropic")


def _org_override(db: Session, org_id: int) -> dict:
    row = db.scalar(select(OrganizationSetting).where(
        OrganizationSetting.org_id == org_id, OrganizationSetting.key == _ASSISTANT_SETTING_KEY))
    return dict(row.value) if row and isinstance(row.value, dict) else {}


def resolve_config(db: Session, org_id: int) -> AssistantConfig:
    """Effective config: per-org override (admin UI) wins over env defaults; blanks fall back."""
    o = _org_override(db, org_id)

    def pick(key: str, env_default):
        v = o.get(key)
        return v if v not in (None, "") else env_default

    return AssistantConfig(
        provider=pick("provider", settings.assistant_provider),
        base_url=pick("base_url", settings.assistant_base_url),
        model=pick("model", settings.assistant_model),
        api_key=pick("api_key", settings.assistant_api_key),
        system_prompt=pick("system_prompt", _SYSTEM_PROMPT),
        timeout=_as_int(pick("timeout", settings.assistant_timeout), settings.assistant_timeout),
        max_steps=_as_int(pick("max_steps", settings.assistant_max_steps),
                          settings.assistant_max_steps),
    )


def set_org_config(db: Session, org_id: int, patch: dict) -> dict:
    """Upsert the per-org assistant config. A blank api_key leaves the stored one unchanged."""
    row = db.scalar(select(OrganizationSetting).where(
        OrganizationSetting.org_id == org_id, OrganizationSetting.key == _ASSISTANT_SETTING_KEY))
    current = dict(row.value) if row and isinstance(row.value, dict) else {}
    for k, v in patch.items():
        if k == "api_key" and (v is None or v == ""):
            continue  # never clobber a stored key with a blank submit
        current[k] = v
    if row is None:
        row = OrganizationSetting(org_id=org_id, key=_ASSISTANT_SETTING_KEY, value=current)
        db.add(row)
    else:
        row.value = current
    db.flush()
    return current


def public_config(cfg: AssistantConfig) -> dict:
    """Config safe to expose to the admin UI — the API key is never returned, only its presence."""
    return {"enabled": cfg.enabled, "provider": cfg.provider, "base_url": cfg.base_url,
            "model": cfg.model, "system_prompt": cfg.system_prompt, "timeout": cfg.timeout,
            "max_steps": cfg.max_steps, "has_api_key": bool(cfg.api_key)}


# --- Read-only, permission-gated tool registry ------------------------------------------- #

@dataclass
class ChatTool:
    description: str
    permission: str  # caller must hold this; tools they can't use aren't offered to the model
    parameters: dict  # JSON schema
    handler: Callable[[Session, Principal, dict], dict]
    label: str  # human label for the action card
    kind: str = "read"  # read | draft | proposed — drives the action-card styling; drives NOTHING
    #                     that sends/publishes. "draft"/"proposed" create governed records only.


def _t_overview(db, principal, args):
    from app.modules import reporting
    inc = has_permission(db, principal, "donation.view")
    return reporting.overview(db, org_id=principal.org_id, include_donations=inc)


def _t_donation_metrics(db, principal, args):
    from app.modules.donations.service import donation_metrics
    return donation_metrics(db, org_id=principal.org_id)


def _t_open_opportunities(db, principal, args):
    from app.modules.scheduling.service import public_opportunities
    return {"opportunities": public_opportunities(db, org_id=principal.org_id)}


def _t_my_shifts(db, principal, args):
    from app.modules.people.service import profile_for_user
    from app.modules.scheduling.service import my_signups
    profile = profile_for_user(db, org_id=principal.org_id, user_id=principal.user_id)
    if profile is None:
        return {"shifts": [], "note": "no volunteer profile"}
    return {"shifts": my_signups(db, org_id=principal.org_id, profile_id=profile.id)}


def _t_draft_social_post(db, principal, args):
    """Create a social-post DRAFT (never published — publishing stays a human R4 action)."""
    from app.modules.social.models import PostSource
    from app.modules.social.service import create_post
    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        return {"error": "a topic/prompt is required"}
    post = create_post(db, org_id=principal.org_id, created_by=principal.user_id, channel_ids=[],
                       source=PostSource.llm_assisted, prompt=prompt)
    return {"post_id": post.id, "body": post.body,
            "note": "Saved as a draft in Social — a human must review, approve, and publish it."}


def _t_propose_waitlist_promotion(db, principal, args):
    """File an approval PROPOSAL to promote the next waitlisted person — awaits human approval."""
    from app.modules.training.service import propose_waitlist_promotion
    session_id = args.get("session_id")
    if session_id is None:
        return {"error": "session_id is required"}
    proposal = propose_waitlist_promotion(db, org_id=principal.org_id, session_id=int(session_id),
                                          requested_by_user_id=principal.user_id)
    if proposal is None:
        return {"proposed": False, "reason": "no eligible waitlisted candidate or no free seat"}
    return {"proposal_id": proposal.id, "status": proposal.status.value,
            "note": "Filed for human approval — nothing changes until an admin approves it."}


CHAT_TOOLS: dict[str, ChatTool] = {
    "get_overview": ChatTool(
        "Operational overview: active volunteers, upcoming shifts, application funnel, hours "
        "(and donation totals for finance staff).", "report.view_staffing",
        {"type": "object", "properties": {}}, _t_overview, "Checked the operations overview"),
    "get_donation_metrics": ChatTool(
        "Donation totals and recurring giving (finance only).", "donation.view",
        {"type": "object", "properties": {}}, _t_donation_metrics, "Checked donation metrics"),
    "list_open_opportunities": ChatTool(
        "Public volunteer opportunities / open shifts to sign up for.", "shift.view_eligible",
        {"type": "object", "properties": {}}, _t_open_opportunities, "Listed open opportunities"),
    "my_upcoming_shifts": ChatTool(
        "The signed-in volunteer's own upcoming shift sign-ups.", "shift.view_eligible",
        {"type": "object", "properties": {}}, _t_my_shifts, "Looked up your shifts"),
    "draft_social_post": ChatTool(
        "Draft a social media post (saved as a draft for a human to review/approve/publish — it is "
        "NOT published).", "social.draft",
        {"type": "object", "properties": {"prompt": {"type": "string",
         "description": "what the post should be about"}}, "required": ["prompt"]},
        _t_draft_social_post, "Drafted a social post (pending review)", kind="draft"),
    "propose_waitlist_promotion": ChatTool(
        "Propose promoting the next waitlisted person into a freed training seat. Files an approval "
        "request — a human must approve; nothing happens automatically.", "training.approve_promotion",
        {"type": "object", "properties": {"session_id": {"type": "integer"}},
         "required": ["session_id"]},
        _t_propose_waitlist_promotion, "Filed a promotion proposal (needs approval)", kind="proposed"),
}


def _available_tools(db: Session, principal: Principal) -> dict[str, ChatTool]:
    return {n: t for n, t in CHAT_TOOLS.items() if has_permission(db, principal, t.permission)}


# --- Providers (tool-call loop; stdlib HTTP, no SDK) ------------------------------------- #

@dataclass
class ChatResult:
    reply: str
    actions: list[dict] = field(default_factory=list)
    provider: str = ""
    model: str = ""


class AssistantError(Exception):
    pass


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                          **headers}, method="POST")
    with _guarded_open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _openai_tool_specs(tools: dict[str, ChatTool]) -> list[dict]:
    return [{"type": "function", "function": {"name": n, "description": t.description,
                                              "parameters": t.parameters}}
            for n, t in tools.items()]


def run_chat(db: Session, principal: Principal, messages: list[dict]) -> ChatResult:
    """Run one governed chat turn. `messages` is the client-held transcript (role/content).
    Returns the assistant reply + a list of read actions taken. Never mutates domain data."""
    cfg = resolve_config(db, principal.org_id)
    if not cfg.enabled:
        return ChatResult(reply="The AI assistant isn't configured yet. An admin can enable it in "
                                "Settings → AI Assistant.", provider="off")
    tools = _available_tools(db, principal)
    # Cap history defensively (stateless server; the client owns memory).
    convo = [{"role": "system", "content": cfg.system_prompt}]
    for m in messages[-20:]:
        role = m.get("role")
        content = str(m.get("content", ""))[:4000]
        if role in ("user", "assistant") and content:
            convo.append({"role": role, "content": content})

    actions: list[dict] = []
    try:
        if cfg.provider == "ollama":
            reply = _loop_ollama(db, principal, cfg, convo, tools, actions)
        elif cfg.provider == "openai":
            reply = _loop_openai(db, principal, cfg, convo, tools, actions)
        else:
            reply = _loop_anthropic(db, principal, cfg, convo, tools, actions)
    except AssistantError:
        raise
    except Exception as exc:  # noqa: BLE001 - never 500 the chat box; surface a friendly reply
        return ChatResult(reply=f"The assistant is unreachable right now ({str(exc)[:120]}). "
                                "Check the AI Assistant settings.", provider=f"{cfg.provider}:error",
                          model=cfg.model)
    return ChatResult(reply=reply, actions=actions, provider=cfg.provider, model=cfg.model)


def stream_chat(db: Session, principal: Principal, messages: list[dict]):
    """Streaming variant: yields events {type: token|action|done|error, ...}. Real token streaming
    for Ollama; Anthropic falls back to a single emitted reply (still governed + tool-using)."""
    cfg = resolve_config(db, principal.org_id)
    if not cfg.enabled:
        yield {"type": "token", "text": "The AI assistant isn't configured yet. An admin can "
                                        "enable it in Settings → AI Assistant."}
        yield {"type": "done", "provider": "off", "model": ""}
        return
    tools = _available_tools(db, principal)
    convo: list[dict] = [{"role": "system", "content": cfg.system_prompt}]
    for m in messages[-20:]:
        role, content = m.get("role"), str(m.get("content", ""))[:4000]
        if role in ("user", "assistant") and content:
            convo.append({"role": role, "content": content})
    actions: list[dict] = []
    try:
        if cfg.provider == "ollama":
            yield from _stream_ollama(db, principal, cfg, convo, tools, actions)
        else:
            res = run_chat(db, principal, messages)
            for a in res.actions:
                yield {"type": "action", **a}
            yield {"type": "token", "text": res.reply}
            yield {"type": "done", "provider": res.provider, "model": res.model}
    except Exception as exc:  # noqa: BLE001 - stream a friendly error, never crash the connection
        yield {"type": "token", "text": f"The assistant is unreachable right now "
                                        f"({str(exc)[:120]})."}
        yield {"type": "done", "provider": f"{cfg.provider}:error", "model": cfg.model}


def _stream_ollama(db, principal, cfg: AssistantConfig, convo: list[dict],
                   tools: dict[str, ChatTool], actions: list[dict]):
    url = cfg.base_url.rstrip("/") + "/api/chat"
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    specs = _openai_tool_specs(tools)
    for _ in range(cfg.max_steps):
        body: dict = {"model": cfg.model, "messages": convo, "stream": True}
        if specs:
            body["tools"] = specs
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers,
                                     method="POST")
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        with _guarded_open(req, timeout=cfg.timeout) as resp:
            for raw in resp:
                line = raw.strip()
                if not line:
                    continue
                chunk = json.loads(line.decode())
                msg = chunk.get("message", {})
                if msg.get("content"):
                    content_parts.append(msg["content"])
                    yield {"type": "token", "text": msg["content"]}
                if msg.get("tool_calls"):
                    tool_calls.extend(msg["tool_calls"])
                if chunk.get("done"):
                    break
        if not tool_calls:
            yield {"type": "done", "provider": "ollama", "model": cfg.model}
            return
        convo.append({"role": "assistant", "content": "".join(content_parts),
                      "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {}
            before = len(actions)
            out = _run_tool(db, principal, tools, fn.get("name", ""), args, actions)
            for a in actions[before:]:
                yield {"type": "action", **a}
            convo.append({"role": "tool", "content": out})
    yield {"type": "token", "text": " (I couldn't finish that in a few steps — try rephrasing.)"}
    yield {"type": "done", "provider": "ollama", "model": cfg.model}


def _run_tool(db: Session, principal: Principal, tools: dict[str, ChatTool], name: str,
              args: dict, actions: list[dict]) -> str:
    tool = tools.get(name)
    if tool is None:
        return f"Tool '{name}' is not available to you."
    try:
        result = tool.handler(db, principal, args or {})
    except Exception as exc:  # noqa: BLE001 - report tool errors back to the model, don't crash
        return f"Tool error: {str(exc)[:200]}"
    actions.append({"kind": tool.kind, "label": tool.label})
    audit.emit(db, org_id=principal.org_id, action="assistant.tool", actor_type="user",
               actor_id=principal.user_id, target_type="chat_tool", target_id=name)
    db.commit()
    return json.dumps(result, default=str)[:6000]


def _loop_ollama(db, principal, cfg: AssistantConfig, convo: list[dict],
                 tools: dict[str, ChatTool], actions: list[dict]) -> str:
    url = cfg.base_url.rstrip("/") + "/api/chat"
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    specs = _openai_tool_specs(tools)
    for _ in range(cfg.max_steps):
        body = {"model": cfg.model, "messages": convo, "stream": False}
        if specs:
            body["tools"] = specs
        data = _post_json(url, body, headers, cfg.timeout)
        msg = data.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return (msg.get("content") or "").strip()
        convo.append(msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {}
            out = _run_tool(db, principal, tools, fn.get("name", ""), args, actions)
            convo.append({"role": "tool", "content": out})
    return "I wasn't able to complete that in a few steps — try rephrasing."


def _loop_openai(db, principal, cfg: AssistantConfig, convo: list[dict],
                 tools: dict[str, ChatTool], actions: list[dict]) -> str:
    """OpenAI-compatible chat (OpenAI, Ollama Cloud, OpenRouter, LiteLLM, vLLM, ...). base_url
    should include the API root (e.g. https://api.openai.com/v1). Bearer key when set."""
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    specs = _openai_tool_specs(tools)
    for _ in range(cfg.max_steps):
        body: dict = {"model": cfg.model, "messages": convo}
        if specs:
            body["tools"] = specs
        data = _post_json(url, body, headers, cfg.timeout)
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return (msg.get("content") or "").strip()
        convo.append(msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {}
            out = _run_tool(db, principal, tools, fn.get("name", ""), args, actions)
            convo.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": out})
    return "I wasn't able to complete that in a few steps — try rephrasing."


def _loop_anthropic(db, principal, cfg: AssistantConfig, convo: list[dict],
                    tools: dict[str, ChatTool], actions: list[dict]) -> str:
    url = cfg.base_url.rstrip("/") + "/v1/messages" if cfg.base_url else \
        "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01"}
    system = convo[0]["content"]
    msgs = [{"role": m["role"], "content": m["content"]} for m in convo[1:]]
    specs = [{"name": n, "description": t.description, "input_schema": t.parameters}
             for n, t in tools.items()]
    for _ in range(cfg.max_steps):
        body = {"model": cfg.model, "system": system, "messages": msgs, "max_tokens": 1024}
        if specs:
            body["tools"] = specs
        data = _post_json(url, body, headers, cfg.timeout)
        blocks = data.get("content", [])
        if data.get("stop_reason") != "tool_use":
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        msgs.append({"role": "assistant", "content": blocks})
        results = []
        for b in blocks:
            if b.get("type") == "tool_use":
                out = _run_tool(db, principal, tools, b.get("name", ""), b.get("input", {}), actions)
                results.append({"type": "tool_result", "tool_use_id": b.get("id"), "content": out})
        msgs.append({"role": "user", "content": results})
    return "I wasn't able to complete that in a few steps — try rephrasing."
