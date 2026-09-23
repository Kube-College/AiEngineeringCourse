from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Controller settings from the environment and `.env`; keys match `.env.example`."""

    model_config = SettingsConfigDict(env_file=".env", extra="forbid", frozen=True)

    agent_backend: Literal["simulated", "openhands"] = "simulated"
    state_dir: Path = Path(".data")
    workspace_dir: Path = Path(".workspaces")
    poll_seconds: PositiveInt = 20
    run_timeout_seconds: PositiveInt = 1200
    max_iterations: PositiveInt = 50
    issue_budget_usd: Annotated[Decimal, Field(gt=0, decimal_places=6)] = Decimal(5)
    dispatch_estimate_microusd: PositiveInt = 1_000_000
    max_fix_cycles: PositiveInt = 1
    completed_retention_hours: PositiveInt = 24
    max_active: Literal[1] = 1
    github_writes_enabled: bool = False
    gh_repo: str = ""
    gh_token: SecretStr = SecretStr("")
    llm_model: str = "openai/gpt-5.6-terra"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://openrouter.ai/api/v1"

    @property
    def issue_budget_microusd(self) -> int:
        return int(self.issue_budget_usd * 1_000_000)
