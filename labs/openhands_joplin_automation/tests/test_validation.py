"""Profiles and commands are owned by the controller."""

from pathlib import Path
import subprocess

import pytest

from openhands_controller.delivery.validation import CandidateValidator, CheckResult, load_qualified_validator


class FakeRunner:
    def __init__(self):
        self.commands = []

    def run_batch(self, *, image, checkout, commands, timeout, mounts, base_sha):
        self.commands.extend(commands)
        return [CheckResult(exit_code=0, stdout="pass", stderr="", timed_out=False) for _ in commands]


@pytest.fixture
def validation_harness(tmp_path: Path):
    def make():
        runner = FakeRunner()
        checkout = tmp_path / "candidate"
        checkout.mkdir(exist_ok=True)
        def git(*args):
            return subprocess.run(["git", "-C", str(checkout), "-c", "core.hooksPath=/dev/null", *args],
                                  check=True, capture_output=True, text=True).stdout.strip()
        git("init")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "Test")
        (checkout / "marker").write_text("baseline\n")
        git("add", "marker")
        git("commit", "-m", "baseline")
        base_sha = git("rev-parse", "HEAD")
        (checkout / "marker").write_text("candidate\n")
        git("commit", "-am", "candidate")
        candidate_sha = git("rev-parse", "HEAD")
        profile_commands = [["node", ".yarn/releases/yarn-4.16.0.cjs", "workspace", "@joplin/lib", "tsc"]]
        validator = CandidateValidator(
            checkout_provider=lambda sha: checkout if sha == candidate_sha else None,
            image_digest="sha256:" + "b" * 64,
            base_sha=base_sha,
            profiles={"core-16638": {"commands": profile_commands, "patches": []}},
            runner=runner, evidence_root=tmp_path / "evidence",
        )
        return validator, runner, profile_commands, candidate_sha
    return make


def test_validation_ignores_agent_supplied_command(validation_harness):
    validator, runner, commands, candidate_sha = validation_harness()
    result = validator.validate_candidate(candidate_sha, "core-16638", agent_output={"command": "true"})
    assert runner.commands == commands
    assert result.candidate_sha == candidate_sha
    assert result.passed


def test_validation_rejects_unknown_profile(validation_harness):
    validator, runner, _, candidate_sha = validation_harness()
    with pytest.raises(ValueError, match="profile"):
        validator.validate_candidate(candidate_sha, "skip-checks")
    assert runner.commands == []


def test_validation_fails_closed_on_timeout(validation_harness):
    validator, runner, _, candidate_sha = validation_harness()
    runner.run_batch = lambda **_: [CheckResult(exit_code=None, stdout="", stderr="timeout", timed_out=True)]
    result = validator.validate_candidate(candidate_sha, "core-16638")
    assert not result.passed
    assert Path(result.evidence_dir, "result.json").exists()


def test_validation_rejects_mismatched_baseline(validation_harness):
    validator, runner, _, candidate_sha = validation_harness()
    validator.base_sha = "0" * 40
    result = validator.validate_candidate(candidate_sha, "core-16638")
    assert not result.passed
    assert runner.commands == []


def test_live_validator_requires_qualified_manifest(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        load_qualified_validator(tmp_path, checkout_provider=lambda _: None,
                                 runner=FakeRunner(), evidence_root=tmp_path / "evidence")


def test_validation_records_runner_failure(validation_harness):
    validator, runner, _, candidate_sha = validation_harness()
    def fail(**_):
        raise OSError("Docker unavailable")
    runner.run_batch = fail
    result = validator.validate_candidate(candidate_sha, "core-16638")
    assert not result.passed
    assert Path(result.evidence_dir, "result.json").exists()


def test_validation_applies_trusted_patch_in_disposable_checkout(validation_harness, tmp_path):
    validator, runner, _, candidate_sha = validation_harness()
    regressions = tmp_path / "regressions"
    regressions.mkdir()
    (regressions / "assertion.patch").write_text(
        "--- a/marker\n+++ b/marker\n@@ -1 +1 @@\n-candidate\n+candidate with regression\n"
    )
    validator.regression_root = regressions
    validator.profiles["core-16638"]["patches"] = ["assertion.patch"]
    observed = []
    def run_batch(**arguments):
        observed.append((arguments["checkout"] / "marker").read_text())
        return [CheckResult(exit_code=0, stdout="pass", stderr="", timed_out=False)]
    runner.run_batch = run_batch
    result = validator.validate_candidate(candidate_sha, "core-16638")
    assert result.passed
    assert observed == ["candidate with regression\n"]
    assert (validator.checkout_provider(candidate_sha) / "marker").read_text() == "candidate\n"
