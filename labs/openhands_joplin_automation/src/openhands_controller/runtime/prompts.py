"""OpenHands model configuration and role contracts."""

import json

from ..config import Settings
from ..domain.results import ROLE_RESULTS
from ..domain.states import Role


def build_llm_config(settings: Settings) -> dict[str, object]:
    """Return OpenHands 1.48 LLM arguments with one explicit OpenRouter route."""
    if not settings.llm_api_key.get_secret_value():
        raise ValueError("OpenRouter key is required for live execution")
    if (settings.llm_model != "openai/gpt-5.6-terra"
            or settings.llm_base_url != "https://openrouter.ai/api/v1"):
        raise ValueError("OpenRouter model and endpoint must match the qualified route")
    return {
        "usage_id": "joplin-agent",
        "model": "openrouter/" + settings.llm_model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "num_retries": 0,
    }


def role_prompt(role: Role | str, *, issue_title: str, issue_body: str,
                candidate_sha: str | None = None) -> str:
    """Give the agent work context and a strict data-only final result schema."""
    selected = Role(role)
    if selected == Role.REVIEW and not candidate_sha:
        raise ValueError("review requires candidate SHA")
    schema = ROLE_RESULTS[selected].model_json_schema()
    review = f"Review candidate SHA {candidate_sha}. Inspect the diff and validation evidence. " if selected == Role.REVIEW else ""
    return (
        f"Role: {selected.value}. Issue: {issue_title}\n{issue_body}\n"
        + review
        + "Inspect and edit only the assigned workspace. The controller owns commits, validation and publication. "
          "Finish with a single JSON object matching this schema. Do not wrap it in Markdown.\n"
        + json.dumps(schema, sort_keys=True)
    )
