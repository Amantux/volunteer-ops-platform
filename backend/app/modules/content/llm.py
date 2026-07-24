"""LLM drafting assist (optional). First LLM integration; shared shape for future features.

Mirrors the email `EmailAdapter`/`get_adapter` pattern: a provider Protocol selected by config,
with a deterministic dev provider as the DEFAULT so the platform works with no API key and CI is
stable. AI is strictly an assist — output is returned to the human editor as a draft suggestion,
never published automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

_MAX_PROMPT = 2000
_MAX_OUTPUT = 1200


@dataclass
class DraftResult:
    text: str
    provider: str


class LLMProvider(Protocol):
    def draft_copy(self, *, prompt: str, context: dict) -> DraftResult: ...


class DevDraftProvider:
    """Deterministic, network-free draft generator. Default provider + the 'AI unavailable'
    fallback. Produces plausible placeholder copy from the prompt so the editor flow works and
    tests are stable — same input always yields the same output."""

    name = "dev"

    def draft_copy(self, *, prompt: str, context: dict) -> DraftResult:
        topic = (prompt or "your organization").strip()[:200]
        org = str(context.get("org_name", "our organization"))
        text = (
            f"{topic.capitalize()}.\n\n"
            f"At {org}, we bring neighbours together to make a real difference. "
            f"Whether you have an hour or a whole day, there's a place for you here — "
            f"no experience required, just a willingness to help.\n\n"
            f"Get involved today and see the impact your time can have."
        )
        return DraftResult(text=text[:_MAX_OUTPUT], provider=self.name)


class AnthropicProvider:
    """Real provider. Imported lazily so the SDK is only required when configured."""

    name = "anthropic"

    def draft_copy(self, *, prompt: str, context: dict) -> DraftResult:
        import anthropic  # lazy — only needed when llm_provider == "anthropic"

        client = anthropic.Anthropic(api_key=settings.llm_api_key)
        org = str(context.get("org_name", "the organization"))
        system = (
            "You are a helpful copywriter for a volunteer organization's public website. "
            "Write warm, plain-language, inclusive copy. Return prose only — no markdown, "
            "no HTML, no preamble."
        )
        message = client.messages.create(
            model=settings.llm_model or "claude-sonnet-5",
            max_tokens=800,
            system=system,
            messages=[{"role": "user",
                       "content": f"Organization: {org}\n\nWrite website copy for: {prompt[:_MAX_PROMPT]}"}],
        )
        parts = [b.text for b in message.content if getattr(b, "type", None) == "text"]
        return DraftResult(text="\n".join(parts).strip()[:_MAX_OUTPUT], provider=self.name)


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "anthropic" and settings.llm_api_key:
        return AnthropicProvider()
    return DevDraftProvider()


def draft_copy(*, prompt: str, context: dict) -> DraftResult:
    """Generate a copy suggestion, failing safe to the dev provider if the real one errors."""
    provider = get_llm_provider()
    try:
        return provider.draft_copy(prompt=prompt[:_MAX_PROMPT], context=context)
    except Exception:  # noqa: BLE001 - AI is optional; never break the editor flow
        return DevDraftProvider().draft_copy(prompt=prompt[:_MAX_PROMPT], context=context)
