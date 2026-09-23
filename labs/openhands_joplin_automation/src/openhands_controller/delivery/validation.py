"""Run only controller-owned checks in a disposable candidate checkout."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol
from uuid import uuid4

from ..domain.models import ValidationResult


@dataclass(frozen=True)
class CheckResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool


class ContainerRunner(Protocol):
    def run_batch(self, *, image: str, checkout: Path, commands: list[list[str]],
                  timeout: int, mounts: tuple[tuple[Path, str], ...],
                  base_sha: str) -> list[CheckResult]: ...


class DockerValidationRunner:
    def run_batch(self, *, image: str, checkout: Path, commands: list[list[str]],
                  timeout: int, mounts: tuple[tuple[Path, str], ...],
                  base_sha: str) -> list[CheckResult]:
        argv = ["docker", "create", "--network", "none", "--security-opt", "no-new-privileges",
                "--cap-drop", "ALL", "--pids-limit", "1024", "--workdir", "/opt/joplin"]
        for source, target in mounts:
            argv.extend(["--mount", f"type=bind,source={source},target={target},readonly"])
        argv.extend(["--entrypoint", "/bin/sleep", image, str(max(1200, timeout * len(commands) + 120))])
        container = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=True).stdout.strip()
        try:
            subprocess.run(["docker", "start", container], capture_output=True, text=True, timeout=30, check=True)
            changed = subprocess.run(
                ["git", "-C", str(checkout), "-c", "core.hooksPath=/dev/null",
                 "diff", "--name-only", "-z", base_sha],
                capture_output=True, timeout=30, check=True,
            ).stdout.split(b"\0")
            untracked = subprocess.run(
                ["git", "-C", str(checkout), "-c", "core.hooksPath=/dev/null",
                 "ls-files", "--others", "--exclude-standard", "-z"],
                capture_output=True, timeout=30, check=True,
            ).stdout.split(b"\0")
            created_parents: set[str] = set()
            for raw in sorted(set(changed + untracked)):
                if not raw:
                    continue
                name = raw.decode("utf-8", "surrogateescape")
                source = checkout / name
                if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(checkout.resolve()):
                    raise ValueError(f"unsafe validation file: {name}")
                parent = str((Path("/opt/joplin") / name).parent)
                if parent not in created_parents:
                    subprocess.run(["docker", "exec", container, "/bin/mkdir", "-p", "--", parent],
                                   capture_output=True, timeout=30, check=True)
                    created_parents.add(parent)
                subprocess.run(["docker", "cp", str(source), f"{container}:/opt/joplin/{name}"],
                               capture_output=True, timeout=30, check=True)
            results = []
            for command in commands:
                try:
                    process = subprocess.run(["docker", "exec", "--workdir", "/opt/joplin", container, *command],
                                             capture_output=True, text=True, timeout=timeout)
                    result = CheckResult(process.returncode, process.stdout, process.stderr, False)
                except subprocess.TimeoutExpired as error:
                    result = CheckResult(None, str(error.stdout or ""), str(error.stderr or ""), True)
                except OSError as error:
                    result = CheckResult(None, "", str(error), False)
                results.append(result)
                if result.timed_out or result.exit_code != 0:
                    break
            return results
        finally:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)


class CandidateValidator:
    def __init__(self, *, checkout_provider: Callable[[str], Path | None], image_digest: str,
                 base_sha: str, profiles: dict[str, dict[str, object]], runner: ContainerRunner,
                 evidence_root: Path, regression_root: Path | None = None, timeout_seconds: int = 600):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest):
            raise ValueError("qualified image digest required")
        if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
            raise ValueError("pinned base SHA required")
        self.checkout_provider = checkout_provider
        self.image_digest = image_digest
        self.base_sha = base_sha
        self.profiles = profiles
        self.runner = runner
        self.evidence_root = Path(evidence_root)
        self.regression_root = Path(regression_root) if regression_root else None
        self.timeout_seconds = timeout_seconds

    def validate_candidate(self, candidate_sha: str, profile: str,
                           agent_output: dict[str, object] | None = None) -> ValidationResult:
        # Agent output is intentionally data-only; it never selects argv or profile files.
        del agent_output
        if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
            raise ValueError("full candidate SHA required")
        trusted_profile = self.profiles.get(profile)
        if trusted_profile is None:
            raise ValueError("unknown validation profile")
        evidence = self.evidence_root / candidate_sha / profile / uuid4().hex
        evidence.mkdir(parents=True, exist_ok=False)
        started = datetime.now(timezone.utc).isoformat()
        def finish(passed: bool, checks: list[dict[str, object]]) -> ValidationResult:
            manifest = {"candidate_sha": candidate_sha, "base_sha": self.base_sha, "profile": profile,
                        "image_digest": self.image_digest, "started_at": started, "passed": passed,
                        "checks": checks}
            (evidence / "result.json").write_text(json.dumps(manifest, indent=2) + "\n")
            return ValidationResult(candidate_sha=candidate_sha, profile=profile,
                                    passed=passed, evidence_dir=str(evidence))
        try:
            source = self.checkout_provider(candidate_sha)
            if source is None or not source.is_dir() or not (source / ".git").exists():
                return finish(False, [{"kind": "identity", "error": "candidate checkout missing"}])
            head = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, timeout=15, check=True).stdout.strip()
            parent = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD^"],
                                    capture_output=True, text=True, timeout=15, check=True).stdout.strip()
            if head != candidate_sha or parent != self.base_sha:
                return finish(False, [{"kind": "identity", "error": "candidate or baseline SHA mismatch"}])
        except (ValueError, OSError, subprocess.SubprocessError):
            return finish(False, [{"kind": "identity", "error": "candidate identity unavailable"}])
        commands = trusted_profile.get("commands")
        patches = trusted_profile.get("patches")
        if not isinstance(commands, list) or not commands or not all(
            isinstance(command, list) and command and all(isinstance(word, str) and word for word in command)
            for command in commands
        ) or not isinstance(patches, list) or not all(isinstance(item, str) for item in patches):
            raise ValueError("trusted validation profile malformed")
        checks: list[dict[str, object]] = []
        passed = True
        with tempfile.TemporaryDirectory(prefix="joplin-validation-") as temporary:
            checkout = Path(temporary) / "joplin"
            git_env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
                       "GIT_CONFIG_SYSTEM": os.devnull, "GIT_LFS_SKIP_SMUDGE": "1"}
            try:
                subprocess.run(
                    ["git", "-c", "core.hooksPath=/dev/null", "clone", "--no-hardlinks",
                     "--no-checkout", "--", str(source), str(checkout)],
                    capture_output=True, timeout=120, check=True, env=git_env,
                )
                subprocess.run(
                    ["git", "-C", str(checkout), "-c", "core.hooksPath=/dev/null",
                     "checkout", "--detach", candidate_sha],
                    capture_output=True, timeout=120, check=True, env=git_env,
                )
            except (OSError, subprocess.SubprocessError):
                return finish(False, [{"kind": "checkout", "error": "exact candidate commit unavailable"}])
            for patch_name in patches:
                if self.regression_root is None or Path(patch_name).name != patch_name:
                    raise ValueError("invalid trusted regression patch")
                patch = self.regression_root / patch_name
                if not patch.is_file():
                    passed = False
                    checks.append({"kind": "patch", "name": patch_name, "error": "missing trusted patch"})
                    break
                applied = subprocess.run(
                    ["git", "-C", str(checkout), "-c", "core.hooksPath=/dev/null", "apply", "--", str(patch)],
                    capture_output=True, text=True, timeout=30,
                )
                if applied.returncode:
                    passed = False
                    checks.append({"kind": "patch", "name": patch_name, "error": applied.stderr[:500]})
                    break
            if passed and "playwright_spec" in trusted_profile:
                if self.regression_root is None:
                    raise ValueError("trusted Playwright source required")
                spec = self.regression_root.parent / str(trusted_profile["playwright_spec"])
                if not spec.is_file() or spec.name != trusted_profile["playwright_spec"]:
                    raise ValueError("trusted Playwright spec missing")
                target = checkout / "packages/app-desktop/integration-tests" / spec.name
                shutil.copy2(spec, target)
            if passed:
                try:
                    results = self.runner.run_batch(
                        image=self.image_digest, checkout=checkout, commands=commands,
                        timeout=self.timeout_seconds,
                        mounts=((self.regression_root, "/trusted-regressions"),) if self.regression_root else (),
                        base_sha=self.base_sha,
                    )
                except (OSError, subprocess.SubprocessError, ValueError):
                    return finish(False, checks + [{"kind": "runner", "error": "container check unavailable"}])
                for index, result in enumerate(results):
                    (evidence / f"check-{index:02d}.stdout").write_text(result.stdout)
                    (evidence / f"check-{index:02d}.stderr").write_text(result.stderr)
                    checks.append({"kind": "command", "argv": commands[index], "exit_code": result.exit_code,
                                   "timed_out": result.timed_out})
                    if result.timed_out or result.exit_code != 0:
                        passed = False
                        break
                if len(results) != len(commands):
                    passed = False
        return finish(passed, checks)


def load_qualified_validator(lab_root: Path, *, checkout_provider: Callable[[str], Path | None],
                             runner: ContainerRunner, evidence_root: Path) -> CandidateValidator:
    """Enable live validation only after the image and Linux profiles are qualified."""
    root = Path(lab_root)
    manifest = json.loads((root / "docker/versions.json").read_text())
    catalogue = json.loads((root / "validation/profiles.json").read_text())
    if catalogue.get("qualification") != "linux-qualified":
        raise ValueError("Joplin validation profiles have not passed Linux qualification")
    if manifest.get("joplin_sha") != catalogue.get("base_sha"):
        raise ValueError("Joplin image and validation baseline disagree")
    if manifest.get("agent_server_version") != "1.48.0":
        raise ValueError("unqualified Agent Server version")
    if not re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", str(manifest.get("base_image_digest"))):
        raise ValueError("base image digest missing")
    if manifest.get("package_manager") != "yarn@4.16.0":
        raise ValueError("unqualified Joplin package manager")
    return CandidateValidator(
        checkout_provider=checkout_provider,
        image_digest=manifest["built_image_digest"],
        base_sha=manifest["joplin_sha"],
        profiles=catalogue["profiles"], runner=runner,
        evidence_root=evidence_root,
        regression_root=root / "validation/regressions",
    )
