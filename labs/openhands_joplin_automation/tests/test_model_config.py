import pytest
import subprocess
import sys
from pathlib import Path

from openhands_controller.config import Settings
from openhands_controller.runtime.prompts import build_llm_config, role_prompt


def test_model_route_is_openrouter():
    settings = Settings(_env_file=None, llm_api_key="dummy-openrouter-key")
    config = build_llm_config(settings)
    assert config["model"] == "openrouter/openai/gpt-5.6-terra"
    assert config["base_url"] == "https://openrouter.ai/api/v1"
    assert config["api_key"] == settings.llm_api_key
    assert config["num_retries"] == 0
    assert "dummy-openrouter-key" not in repr(settings)
    assert "dummy-openrouter-key" not in repr(config)


def test_model_route_rejects_missing_key_and_changed_provider():
    with pytest.raises(ValueError, match="OpenRouter key"):
        build_llm_config(Settings(_env_file=None))
    with pytest.raises(ValueError, match="OpenRouter model"):
        build_llm_config(Settings(_env_file=None, llm_api_key="dummy", llm_model="openai/gpt-5.6-terra",
                                  llm_base_url="https://api.openai.com/v1"))


def test_review_prompt_is_tied_to_candidate_sha():
    prompt = role_prompt("review", issue_title="Fix title", issue_body="Keep underscores",
                         candidate_sha="abc123")
    assert "abc123" in prompt
    assert "candidate_sha" in prompt
    assert "verdict" in prompt
    assert "GitHub" not in prompt


def test_smoke_reports_missing_prerequisites_without_calling_model():
    script = Path(__file__).resolve().parents[1] / "scripts/qualify_openhands.py"
    result = subprocess.run([sys.executable, str(script), "--smoke"], capture_output=True,
                            text=True, env={"PATH": "/usr/bin:/bin", "LLM_API_KEY": ""})
    assert result.returncode == 2
    assert "OpenRouter key" in result.stdout
