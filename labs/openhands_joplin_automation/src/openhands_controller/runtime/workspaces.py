"""Persistent, owned Docker Agent Server workspaces."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.request import urlopen

from ..domain.models import IssueKey
from ..persistence.store import Store


SDK_VERSION = "1.48.0"
STATE_VERSION = 1
IMAGE_REPOSITORY = "ghcr.io/openhands/agent-server"
OWNER_LABEL = "dev.openhands.joplin.owner"
WORKSPACE_LABEL = "dev.openhands.joplin.workspace"
IMAGE_LABEL = "dev.openhands.joplin.image"
STORAGE_LABEL = "dev.openhands.joplin.storage"
BASE_LABEL = "dev.openhands.joplin.base"


@dataclass(frozen=True)
class ContainerInfo:
    id: str
    name: str
    running: bool
    image: str
    labels: dict[str, str]
    host_port: int | None


@dataclass(frozen=True)
class ContainerSpec:
    name: str
    image: str
    labels: dict[str, str]
    mounts: tuple[tuple[str, str], ...]
    environment: dict[str, str]
    auth_env_file: str
    publish_host: str = "127.0.0.1"
    server_auth_enabled: bool = True


class DockerPort(Protocol):
    def inspect(self, name: str) -> ContainerInfo | None: ...
    def run(self, spec: ContainerSpec) -> ContainerInfo: ...
    def stop(self, name: str) -> None: ...
    def kill(self, name: str) -> None: ...
    def remove(self, name: str) -> None: ...


class DockerCLI:
    """Small Docker CLI boundary; no shell and no host credentials in containers."""

    @staticmethod
    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=90, check=True)

    def inspect(self, name: str) -> ContainerInfo | None:
        result = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, timeout=15)
        if result.returncode:
            if "no such object" in result.stderr.casefold() or "no such container" in result.stderr.casefold():
                return None
            raise RuntimeError("Docker inspection unavailable")
        data = json.loads(result.stdout)[0]
        ports = (data.get("NetworkSettings") or {}).get("Ports") or {}
        bindings = ports.get("8000/tcp") or []
        port = int(bindings[0]["HostPort"]) if bindings else None
        return ContainerInfo(
            id=data["Id"], name=data["Name"].lstrip("/"),
            running=bool(data["State"]["Running"]), image=data["Config"]["Image"],
            labels=data["Config"].get("Labels") or {}, host_port=port,
        )

    def run(self, spec: ContainerSpec) -> ContainerInfo:
        args = ["run", "-d", "--rm", "--name", spec.name,
                "--publish", f"{spec.publish_host}::8000", "--env-file", spec.auth_env_file]
        for source, target in spec.mounts:
            args.extend(["--mount", f"type=bind,source={source},target={target}"])
        for name, value in spec.labels.items():
            args.extend(["--label", f"{name}={value}"])
        for name, value in spec.environment.items():
            args.extend(["--env", f"{name}={value}"])
        args.extend([spec.image, "--host", "0.0.0.0", "--port", "8000"])
        self._run(args)
        info = self.inspect(spec.name)
        if info is None or not info.running or info.host_port is None:
            raise RuntimeError("Agent Server container did not start")
        health_url = f"http://127.0.0.1:{info.host_port}/health"
        for _ in range(120):
            try:
                with urlopen(health_url, timeout=1) as response:
                    if response.status == 200:
                        return info
            except OSError:
                pass
            time.sleep(1)
        raise RuntimeError("Agent Server did not become healthy")

    def stop(self, name: str) -> None:
        self._run(["stop", "--time", "5", name])

    def kill(self, name: str) -> None:
        self._run(["kill", name])

    def remove(self, name: str) -> None:
        result = subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=30)
        if result.returncode and not any(
            message in result.stderr.casefold() for message in ("no such container", "no such object")
        ):
            raise RuntimeError(f"Docker removal unavailable: {result.stderr.strip()[:200]}")


class WorkspaceManager:
    """Reattach or recreate only labelled workspaces with intact saved storage."""

    def __init__(self, store: Store, root: Path, *, docker: DockerPort,
                 server_token: str, retention_hours: int = 24,
                 image_repository: str | None = IMAGE_REPOSITORY):
        if not server_token:
            raise ValueError("Agent Server authentication token required")
        if image_repository not in (None, IMAGE_REPOSITORY):
            raise ValueError("unsupported image repository")
        self.store = store
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.docker = docker
        self.server_token = server_token
        self.retention = timedelta(hours=retention_hours)
        self.image_repository = image_repository
        self._auth_hash = hashlib.sha256(server_token.encode()).hexdigest()

    def _identifier(self, issue: IssueKey) -> str:
        digest = hashlib.sha256(f"{self.root}:{issue[0]}#{issue[1]}".encode()).hexdigest()[:20]
        return f"workspace-{digest}"

    def identifier(self, issue: IssueKey) -> str:
        """Return the durable workspace identity before the dispatch is persisted."""
        return self._identifier(issue)

    def _image(self, digest: str) -> str:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("full image digest required")
        return f"{self.image_repository}@{digest}" if self.image_repository else digest

    def record(self, workspace_id: str) -> dict[str, object]:
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if row is None:
            raise KeyError(workspace_id)
        return dict(row)

    def _validate(self, row: dict[str, object]) -> None:
        identifier = row["id"]
        if row["schema_version"] != STATE_VERSION or row["sdk_version"] != SDK_VERSION:
            raise ValueError("saved workspace state version is incompatible")
        if row["owned"] != 1 or row["auth_hash"] != self._auth_hash:
            raise ValueError("workspace ownership or authentication mismatch")
        if row["storage_id"] != str(self.root / identifier):
            raise ValueError("saved workspace storage path mismatch")
        if not (self.root / identifier).is_dir():
            raise ValueError("saved workspace storage is missing")
        if row["status"] == "cleaned":
            raise ValueError("workspace was cleaned")
        self._image(str(row["image_digest"]))

    def _spec(self, row: dict[str, object]) -> ContainerSpec:
        identifier = str(row["id"])
        auth_dir = self.root / ".auth"
        auth_dir.mkdir(mode=0o700, exist_ok=True)
        env_file = auth_dir / f"{identifier}.env"
        descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(f"SESSION_API_KEY={self.server_token}\n")
        env_file.chmod(0o600)
        return ContainerSpec(
            name=f"openhands-joplin-{identifier}", image=self._image(str(row["image_digest"])),
            labels={OWNER_LABEL: "course-lab", WORKSPACE_LABEL: identifier,
                    IMAGE_LABEL: str(row["image_digest"]), BASE_LABEL: str(row["base_sha"]),
                    STORAGE_LABEL: hashlib.sha256(str(row["storage_id"]).encode()).hexdigest()},
            mounts=((str(self.root / identifier), "/workspace"),),
            environment={
                "OH_PERSISTENCE_DIR": "/workspace/.openhands",
                # Each workspace has one deterministic container name. A prior
                # container's lease must not block immediate recovery after
                # Docker removes it and starts the replacement.
                "OH_LEASE_TTL_SECONDS": "0",
            },
            auth_env_file=str(env_file),
        )

    @staticmethod
    def _check_info(info: ContainerInfo, spec: ContainerSpec) -> None:
        if info.name != spec.name or info.image != spec.image or any(
            info.labels.get(key) != value for key, value in spec.labels.items()
        ):
            raise ValueError("container ownership or image mismatch")

    def ensure(self, issue: IssueKey, base_sha: str, image_digest: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
            raise ValueError("full base SHA required")
        self._image(image_digest)
        identifier = self._identifier(issue)
        try:
            row = self.record(identifier)
        except KeyError:
            storage = self.root / identifier
            storage.mkdir(mode=0o700, exist_ok=True)
            with self.store.transaction() as db:
                db.execute(
                    "INSERT INTO workspaces(id,repo,issue_number,status,image_digest,storage_id,base_sha,schema_version,sdk_version,owned,auth_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (identifier, *issue, "provisioning", image_digest, str(storage), base_sha,
                     STATE_VERSION, SDK_VERSION, 1, self._auth_hash),
                )
            row = self.record(identifier)
        self._validate(row)
        if row["base_sha"] != base_sha:
            raise ValueError("saved workspace base SHA mismatch")
        if row["image_digest"] != image_digest:
            raise ValueError("saved workspace image digest mismatch")
        self.reattach(identifier)
        return identifier

    def reattach(self, workspace_id: str) -> None:
        row = self.record(workspace_id)
        self._validate(row)
        spec = self._spec(row)
        info = self.docker.inspect(spec.name)
        if info is not None:
            self._check_info(info, spec)
            if not info.running:
                # A --rm container can briefly remain inspectable while Docker
                # removes it after stop. Wait for that removal before reusing
                # its deterministic name.
                for _ in range(50):
                    if self.docker.inspect(spec.name) is None:
                        break
                    time.sleep(0.1)
                else:
                    self.docker.remove(spec.name)
                info = None
        if info is None:
            info = self.docker.run(spec)
            self._check_info(info, spec)
        if not info.running or info.host_port is None:
            raise RuntimeError("Agent Server state is not confirmed running")
        with self.store.transaction() as db:
            db.execute("UPDATE workspaces SET container_id=?, host_port=?, status='ready' WHERE id=?",
                       (info.id, info.host_port, workspace_id))

    def stop(self, workspace_id: str) -> None:
        row = self.record(workspace_id)
        self._validate(row)
        spec = self._spec(row)
        info = self.docker.inspect(spec.name)
        if info is not None:
            self._check_info(info, spec)
            if info.running:
                try:
                    self.docker.stop(spec.name)
                except Exception:
                    self.docker.kill(spec.name)
                info = self.docker.inspect(spec.name)
                if info is not None and info.running:
                    self.docker.kill(spec.name)
                    info = self.docker.inspect(spec.name)
                if info is not None and info.running:
                    raise RuntimeError("runtime stop unconfirmed")
        with self.store.transaction() as db:
            db.execute("UPDATE workspaces SET status='stopped', host_port=NULL WHERE id=?", (workspace_id,))

    def endpoint(self, workspace_id: str) -> tuple[str, str]:
        self.reattach(workspace_id)
        row = self.record(workspace_id)
        return f"http://127.0.0.1:{row['host_port']}", self.server_token

    def connect(self, workspace_id: str):
        from openhands.sdk.workspace import RemoteWorkspace

        host, key = self.endpoint(workspace_id)
        return RemoteWorkspace(host=host, api_key=key, working_dir="/workspace")

    def cleanup(self, now: datetime) -> list[str]:
        removed = []
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT w.* FROM workspaces w JOIN workflows f ON (w.repo=f.repo AND w.issue_number=f.issue_number) WHERE w.owned=1 AND f.state='completed' AND w.completed_at IS NOT NULL AND w.status!='cleaned'"
            ).fetchall()
        for raw in rows:
            row = dict(raw)
            if now - datetime.fromisoformat(str(row["completed_at"])) < self.retention:
                continue
            self._validate(row)
            spec = self._spec(row)
            info = self.docker.inspect(spec.name)
            if info is not None:
                self._check_info(info, spec)
                self.stop(str(row["id"]))
                info = self.docker.inspect(spec.name)
                if info is not None:
                    self.docker.remove(spec.name)
            storage = self.root / str(row["id"])
            shutil.rmtree(storage)
            (self.root / ".auth" / f"{row['id']}.env").unlink(missing_ok=True)
            with self.store.transaction() as db:
                db.execute("UPDATE workspaces SET status='cleaned', container_id=NULL, host_port=NULL WHERE id=?",
                           (row["id"],))
            removed.append(str(row["id"]))
        return removed
