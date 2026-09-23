"""Controller capture rejects agent edits outside approved source paths."""

import subprocess
from pathlib import Path

import pytest

from openhands_controller.delivery.candidate import CandidateCapture


def git(root: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *argv],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def source(tmp_path: Path):
    root = tmp_path / "agent" / "joplin"
    root.mkdir(parents=True)
    git(root, "init")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    for name in ("packages/lib/markdownUtils.ts", "packages/app-desktop/gui/PromptDialog.tsx",
                 "packages/lib/models/Note.test.ts", ".gitmodules"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("baseline\n")
    git(root, "add", "-A")
    git(root, "commit", "-m", "baseline", "--date=2020-01-01T00:00:00+00:00")
    base = git(root, "rev-parse", "HEAD")
    trusted = tmp_path / "trusted-source"
    subprocess.run(["git", "clone", "--no-hardlinks", str(root), str(trusted)],
                   check=True, capture_output=True)
    return root, base, CandidateCapture(
        workspace_root=tmp_path / "agent", output_root=tmp_path / "captured",
        baseline_repository=trusted,
    )


def test_capture_accepts_whitespace_and_leading_dash_filename(source):
    root, base, capture = source
    file = root / "packages/lib/- title with spaces.ts"
    file.write_text("export const safe = true;\n")
    sha = capture.capture_candidate("joplin", base)
    assert len(sha) == 40
    snapshot = capture.checkout(sha)
    assert (snapshot / "packages/lib/- title with spaces.ts").read_text() == file.read_text()


def test_capture_rejects_unexpected_head(source):
    root, base, capture = source
    git(root, "commit", "--allow-empty", "-m", "agent rewrote HEAD")
    with pytest.raises(ValueError, match="HEAD"):
        capture.capture_candidate("joplin", base)


@pytest.mark.parametrize("path", [
    "packages/lib/models/Note.test.ts", ".gitmodules", ".git/hooks/pre-commit",
    "validation/profiles.json", "packages/app-desktop/integration-tests/desktop_16261.spec.ts",
    "packages/lib/jest.config.js", "packages/lib/jest.setup.js",
    "packages/lib/testing/test-utils.ts",
])
def test_capture_rejects_trusted_or_hook_changes(source, path):
    root, base, capture = source
    changed = root / path
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("weakened\n")
    with pytest.raises(ValueError, match="(protected|scope|hook)"):
        capture.capture_candidate("joplin", base)


def test_capture_rejects_symlink_escape(source, tmp_path):
    root, base, capture = source
    (root / "packages/lib/escape.ts").symlink_to(tmp_path / "outside.ts")
    with pytest.raises(ValueError, match="symlink"):
        capture.capture_candidate("joplin", base)


def test_capture_does_not_execute_agent_fsmonitor(source, tmp_path):
    root, base, capture = source
    (root / "packages/lib/markdownUtils.ts").write_text("candidate\n")
    marker = tmp_path / "agent-monitor-ran"
    monitor = tmp_path / "monitor.sh"
    monitor.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    monitor.chmod(0o755)
    git(root, "config", "core.fsmonitor", str(monitor))

    capture.capture_candidate("joplin", base)
    assert not marker.exists()


def test_capture_rejects_path_traversal(source):
    _, base, capture = source
    with pytest.raises(ValueError, match="workspace"):
        capture.capture_candidate("../outside", base)


def test_capture_rejects_untracked_source_outside_scope(source):
    root, base, capture = source
    (root / "README.md").write_text("changed\n")
    with pytest.raises(ValueError, match="scope"):
        capture.capture_candidate("joplin", base)


def test_capture_rejects_renamed_protected_test(source):
    root, base, capture = source
    git(root, "mv", "packages/lib/models/Note.test.ts", "packages/lib/models/Note.old.ts")
    with pytest.raises(ValueError, match="protected|deleted"):
        capture.capture_candidate("joplin", base)


def test_capture_requires_separate_trusted_baseline(source):
    root, _, _ = source
    with pytest.raises(ValueError, match="trusted baseline"):
        CandidateCapture(root.parent, root.parent.parent / "output", baseline_repository=root)


def test_capture_output_cannot_be_inside_agent_workspace(source):
    root, _, capture = source
    with pytest.raises(ValueError, match="capture output"):
        CandidateCapture(root.parent, root.parent / "captures",
                         baseline_repository=capture.baseline_repository)


def test_repeated_capture_has_stable_candidate_sha(source):
    root, base, capture = source
    (root / "packages/lib/markdownUtils.ts").write_text("fixed\n")
    first = capture.capture_candidate("joplin", base)
    assert git(capture.checkout(first), "show", "-s", "--format=%aI", first) == git(
        capture.baseline_repository, "show", "-s", "--format=%aI", base
    )
    second = capture.capture_candidate("joplin", base)
    assert second == first
