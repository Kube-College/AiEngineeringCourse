"""Capture an agent's source changes without trusting its Git history or hooks."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath


SHA = re.compile(r"[0-9a-f]{40}\Z")
WORKSPACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}
ALLOWED_ROOTS = ("packages/lib/", "packages/app-desktop/gui/")


def _git(root: Path, *argv: str, timeout: int = 60) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *argv],
        capture_output=True, timeout=timeout,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )
    if result.returncode:
        raise ValueError(f"Git operation failed: {' '.join(argv[:2])}: {result.stderr[:200]!r}")
    return result.stdout


def _paths(output: bytes) -> list[str]:
    return [os.fsdecode(part) for part in output.split(b"\0") if part]


def _supported(path: str) -> bool:
    pure = PurePosixPath(path)
    if path.startswith("/") or ".." in pure.parts or "\\" in path or "\n" in path:
        return False
    if not path.startswith(ALLOWED_ROOTS) or pure.suffix not in SOURCE_SUFFIXES:
        return False
    if any(part in {"node_modules", "__tests__", "integration-tests"} for part in pure.parts):
        return False
    if pure.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".test.js", ".spec.js")):
        return False
    return True


class CandidateCapture:
    def __init__(self, workspace_root: Path, output_root: Path, baseline_repository: Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.baseline_repository = Path(baseline_repository).resolve()
        if self.baseline_repository.is_relative_to(self.workspace_root):
            raise ValueError("trusted baseline must be outside agent workspaces")
        if self.output_root.is_relative_to(self.workspace_root):
            raise ValueError("capture output must be outside agent workspaces")
        self.output_root.mkdir(parents=True, exist_ok=True)

    def checkout(self, candidate_sha: str) -> Path:
        if not SHA.fullmatch(candidate_sha):
            raise ValueError("full candidate SHA required")
        path = self.output_root / candidate_sha
        if not path.is_dir() or _git(path, "rev-parse", "HEAD").decode().strip() != candidate_sha:
            raise ValueError("candidate checkout missing or mismatched")
        return path

    def capture_candidate(self, workspace_id: str, base_sha: str) -> str:
        if not WORKSPACE.fullmatch(workspace_id) or workspace_id in {".", ".."}:
            raise ValueError("invalid workspace id")
        if not SHA.fullmatch(base_sha):
            raise ValueError("full base SHA required")
        root = self.workspace_root / workspace_id
        if not root.is_dir() or root.is_symlink() or root.resolve().parent != self.workspace_root:
            raise ValueError("workspace checkout missing or outside root")
        if not (root / ".git").is_dir():
            raise ValueError("workspace Git directory required")
        # An active hook can act when other tools operate on this checkout.
        hooks = root / ".git" / "hooks"
        if hooks.exists() and any(p.is_file() and not p.name.endswith(".sample") for p in hooks.iterdir()):
            raise ValueError("workspace hook changes are prohibited")
        head = _git(root, "rev-parse", "HEAD").decode().strip()
        if head != base_sha:
            raise ValueError("workspace HEAD differs from pinned baseline")
        _git(self.baseline_repository, "cat-file", "-e", f"{base_sha}^{{commit}}")
        changed = set()
        for argv in (("diff", "--no-renames", "--name-only", "-z", "HEAD"),
                     ("ls-files", "--others", "--exclude-standard", "-z")):
            changed.update(_paths(_git(root, *argv)))
        if not changed:
            raise ValueError("candidate has no changes")
        for name in changed:
            if not _supported(name):
                raise ValueError(f"candidate path outside supported scope or protected: {name}")
            source = root / name
            if source.is_symlink():
                raise ValueError(f"candidate symlink escape: {name}")
            if not source.exists():
                raise ValueError(f"candidate deleted protected source: {name}")
            if not source.is_file():
                raise ValueError(f"candidate non-file: {name}")
            if source.resolve().is_relative_to(root.resolve()) is False:
                raise ValueError(f"candidate symlink escape: {name}")
        staging = Path(tempfile.mkdtemp(prefix="capture-", dir=self.output_root))
        try:
            subprocess.run(
                ["git", "clone", "--no-hardlinks", "--no-checkout", "--", str(self.baseline_repository), str(staging)],
                check=True, capture_output=True, timeout=120,
                env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
            )
            _git(staging, "checkout", "--detach", base_sha)
            for name in sorted(changed):
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / name, target)
            _git(staging, "add", "--", *sorted(changed))
            author_date = _git(self.baseline_repository, "show", "-s", "--format=%aI", base_sha).decode().strip()
            committer_date = _git(self.baseline_repository, "show", "-s", "--format=%cI", base_sha).decode().strip()
            commit = subprocess.run(
                ["git", "-C", str(staging), "-c", "core.hooksPath=/dev/null",
                 "-c", "user.name=Course Controller", "-c", "user.email=controller@example.invalid",
                 "commit", "--no-verify", "-m", "Capture Joplin candidate"],
                capture_output=True, timeout=60,
                env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
                     "GIT_AUTHOR_DATE": author_date, "GIT_COMMITTER_DATE": committer_date},
            )
            if commit.returncode:
                raise ValueError(f"candidate commit failed: {commit.stderr[:200]!r}")
            sha = _git(staging, "rev-parse", "HEAD").decode().strip()
            destination = self.output_root / sha
            if destination.exists():
                shutil.rmtree(staging)
                self.checkout(sha)
            else:
                staging.rename(destination)
            return sha
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging)
            raise
