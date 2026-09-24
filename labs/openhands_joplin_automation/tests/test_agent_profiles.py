"""Role declarations used by the live OpenHands runtime."""

import pytest

from openhands_controller.config import Settings
from openhands_controller.domain.states import Role
from openhands_controller.runtime.prompts import build_gateway_llm_config, role_prompt


def _llm():
    sdk = pytest.importorskip("openhands.sdk")
    settings = Settings(_env_file=None, llm_api_key="dummy-key")
    return sdk.LLM(**build_gateway_llm_config(
        settings, "http://host.docker.internal:18301/api/v1", "gateway-key",
    ))


def test_triage_agent_has_limited_tools_and_stable_system_context():
    from openhands_controller.runtime.agents import build_agent

    agent = build_agent(Role.TRIAGE, _llm())

    assert [tool.name for tool in agent.tools] == ["terminal"]
    assert "Do not implement" in agent.agent_context.system_message_suffix
    assert "controller owns commits" in agent.agent_context.system_message_suffix.lower()
    assert "Issue:" not in agent.agent_context.system_message_suffix
    assert [skill.name for skill in agent.agent_context.skills] == ["joplin-repository"]
    rendered_context = agent.agent_context.get_system_message_suffix()
    assert "Shared note logic lives in `packages/lib`" in rendered_context
    assert "Do not implement" in rendered_context
    assert agent.agent_context.load_user_skills is False
    assert agent.agent_context.load_public_skills is False
    assert agent.agent_context.load_project_skills is False


@pytest.mark.parametrize("role", [Role.IMPLEMENTATION, Role.FIX])
def test_code_change_agents_have_editor_tools(role):
    from openhands_controller.runtime.agents import build_agent

    agent = build_agent(role, _llm())

    assert [tool.name for tool in agent.tools] == ["terminal", "file_editor", "task_tracker"]
    assert [skill.name for skill in agent.agent_context.skills] == ["joplin-repository"]


def test_review_agent_has_separate_instructions_and_limited_tools():
    from openhands_controller.runtime.agents import build_agent

    agent = build_agent(Role.REVIEW, _llm())

    assert [tool.name for tool in agent.tools] == ["terminal"]
    assert "candidate SHA" in agent.agent_context.system_message_suffix
    assert "discard" in agent.agent_context.system_message_suffix.lower()


def test_issue_data_stays_in_task_message():
    message = role_prompt(Role.TRIAGE, issue_title="Broken title", issue_body="Reproduction steps")

    assert "Broken title" in message
    assert "Reproduction steps" in message
    assert "scope" in message
    assert "Do not implement" not in message
