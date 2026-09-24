"""One declaration point for the tools, skills and instructions of each role."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from ..config import Settings
from ..domain.states import Role


CONTENT_DIR = Path(__file__).with_name("agent_content")


@dataclass(frozen=True)
class ModelRoute:
    """OpenRouter model and conservative USD-per-million-token budget rates."""

    name: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    allow_token_fallback: bool = False

    def __post_init__(self) -> None:
        if not self.name or "/" not in self.name or self.name.startswith("openrouter/"):
            raise ValueError("model route must be an OpenRouter model identifier")
        for rate in (self.input_usd_per_million, self.output_usd_per_million):
            if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
                raise ValueError("model route requires positive finite Decimal budget rates")
        if self.allow_token_fallback and self.name != "openai/gpt-5.6-terra":
            raise ValueError("custom model routes require reported provider cost")

    def reserve_microusd(self, input_bytes: int, output_tokens: int) -> int:
        estimate = (input_bytes * self.input_usd_per_million
                    + output_tokens * self.output_usd_per_million)
        return int(estimate.to_integral_value(rounding=ROUND_CEILING))


DEFAULT_MODEL = ModelRoute("openai/gpt-5.6-terra", Decimal("2"), Decimal("12"),
                           allow_token_fallback=True)


@dataclass(frozen=True)
class AgentProfile:
    prompt: str
    tools: tuple[str, ...]
    skills: tuple[str, ...] = ()
    model: ModelRoute | None = None


AGENTS: dict[Role, AgentProfile] = {
    Role.TRIAGE: AgentProfile("triage.md", ("terminal",), ("joplin-repository.md",)),
    Role.IMPLEMENTATION: AgentProfile(
        "implementation.md", ("terminal", "file_editor", "task_tracker"),
        ("joplin-repository.md",),
    ),
    Role.FIX: AgentProfile("fix.md", ("terminal", "file_editor", "task_tracker"),
                           ("joplin-repository.md",)),
    Role.REVIEW: AgentProfile("review.md", ("terminal",), ("joplin-repository.md",)),
}


def resolve_model(role: Role, settings: Settings) -> ModelRoute:
    """Use a role override, or the qualified Terra default from the environment."""
    selected = AGENTS[Role(role)].model
    if selected is not None:
        return selected
    if settings.llm_model != DEFAULT_MODEL.name:
        raise ValueError("global LLM_MODEL requires a priced model route in each agent declaration")
    return DEFAULT_MODEL


def build_agent(role: Role, llm):
    """Build the pinned SDK agent from a reviewed, role-specific declaration."""
    from openhands.sdk import Agent, Tool
    from openhands.sdk.context import AgentContext
    from openhands.sdk.skills import Skill
    from openhands.tools.preset.default import get_default_condenser, register_default_tools

    profile = AGENTS[Role(role)]
    register_default_tools(enable_browser=False)
    common = (CONTENT_DIR / "common.md").read_text(encoding="utf-8").strip()
    instructions = (CONTENT_DIR / profile.prompt).read_text(encoding="utf-8").strip()
    skills = [Skill(name=Path(name).stem,
                    content=(CONTENT_DIR / "skills" / name).read_text(encoding="utf-8"))
              for name in profile.skills]
    return Agent(
        llm=llm,
        tools=[Tool(name=name) for name in profile.tools],
        agent_context=AgentContext(
            skills=skills,
            system_message_suffix=f"{common}\n\n{instructions}",
            load_user_skills=False,
            load_public_skills=False,
            load_project_skills=False,
        ),
        system_prompt_kwargs={"cli_mode": True},
        condenser=get_default_condenser(llm.model_copy(update={"usage_id": "condenser"})),
    )
