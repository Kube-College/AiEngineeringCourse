import pytest

from openhands_controller.budget import Budget
from openhands_controller.store import Store
from support import Harness


@pytest.fixture
def budget(tmp_path):
    store = Store(tmp_path / "budget.sqlite")
    store.create_workflow(("demo/joplin", 1), "r1")
    return Budget(store)


def test_unknown_spend_blocks_next_call(budget):
    assert budget.reserve(("demo/joplin", 1), "req-1", 100_000)
    budget.settle(("demo/joplin", 1), "req-1", None)
    assert not budget.reserve(("demo/joplin", 1), "req-2", 100_000)


def test_duplicate_settlement_is_idempotent_and_conflict_is_rejected(budget):
    issue = ("demo/joplin", 1)
    assert budget.reserve(issue, "req-1", 200_000)
    budget.settle(issue, "req-1", 150_000)
    budget.settle(issue, "req-1", 150_000)
    with pytest.raises(ValueError):
        budget.settle(issue, "req-1", 175_000)
    assert budget.snapshot(issue)["actual_microusd"] == 150_000


def test_cumulative_usage_replay_does_not_add_cost(budget):
    issue = ("demo/joplin", 1)
    budget.reserve(issue, "req-1", 300_000)
    budget.observe_cumulative(issue, "req-1", 120_000)
    budget.observe_cumulative(issue, "req-1", 120_000)
    budget.observe_cumulative(issue, "req-1", 100_000)
    assert budget.snapshot(issue)["reported_microusd"] == 120_000
    budget.settle(issue, "req-1", 120_000)
    assert budget.snapshot(issue)["actual_microusd"] == 120_000
    assert budget.snapshot(issue)["estimated_microusd"] == 300_000


def test_lower_final_report_cannot_restore_budget(budget):
    issue = ("demo/joplin", 1)
    budget.reserve(issue, "req-1", 300_000)
    budget.observe_cumulative(issue, "req-1", 200_000)
    budget.settle(issue, "req-1", 100_000)
    assert budget.snapshot(issue)["actual_microusd"] == 200_000


def test_restart_and_revision_keep_issue_spend(budget):
    issue = ("demo/joplin", 1)
    budget.reserve(issue, "req-1", 1_000_000)
    budget.settle(issue, "req-1", 900_000)
    row = budget.store.workflow(issue)
    budget.store.cas_workflow(issue, row["version"], revision="r2")
    reopened = Budget(Store(budget.store.path))
    assert reopened.snapshot(issue)["actual_microusd"] == 900_000
    assert reopened.reserve(issue, "req-2", 4_100_000)
    assert not reopened.reserve(issue, "req-3", 1)


def test_explicit_increase_never_clears_unknown_spend(budget):
    issue = ("demo/joplin", 1)
    budget.reserve(issue, "req-1", 100_000)
    budget.settle(issue, "req-1", None)
    budget.increase(issue, 10_000_000, "budget-event-1")
    budget.increase(issue, 10_000_000, "budget-event-1")
    assert not budget.reserve(issue, "req-2", 100_000)
    with pytest.raises(ValueError):
        budget.increase(issue, 11_000_000, "budget-event-1")
    budget.settle(issue, "req-1", 50_000)
    assert budget.reserve(issue, "req-2", 100_000)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), "100", True])
def test_invalid_money_values_are_rejected(budget, value):
    with pytest.raises(ValueError):
        budget.reserve(("demo/joplin", 1), "bad", value)


@pytest.mark.parametrize("body", ["/agent budget -1", "/agent budget NaN", "/agent budget inf", "/agent budget 0"])
def test_invalid_budget_command_does_not_change_limit(tmp_path, body):
    h = Harness(tmp_path)
    h.emit("issue")
    h.emit("command", body=body)
    assert h.store.workflow(("demo/joplin", 1))["budget_limit"] == 5_000_000


def test_authorised_budget_command_increases_total_without_resuming(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.emit("command", body="/agent budget 7.50")
    assert h.store.workflow(("demo/joplin", 1))["budget_limit"] == 7_500_000
    assert h.store.workflow(("demo/joplin", 1))["state"] == "queued"
