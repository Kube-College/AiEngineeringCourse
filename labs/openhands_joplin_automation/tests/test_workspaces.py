from datetime import datetime, timedelta, timezone

import pytest

from openhands_controller.persistence.store import Store
from openhands_controller.runtime.workspaces import ContainerInfo, WorkspaceManager


IMAGE = "sha256:" + "b" * 64
BASE = "a" * 40


class FakeDocker:
    def __init__(self):
        self.containers = {}
        self.runs = []
        self.removed = []
        self.fail_stop = False
        self.fail_kill = False

    def inspect(self, name):
        return self.containers.get(name)

    def run(self, spec):
        self.runs.append(spec)
        info = ContainerInfo(id=f"container-{len(self.runs)}", name=spec.name, running=True,
                             image=spec.image, labels=spec.labels, host_port=8123)
        self.containers[spec.name] = info
        return info

    def stop(self, name):
        if self.fail_stop:
            raise TimeoutError("no stop confirmation")
        self.containers.pop(name, None)

    def kill(self, name):
        if self.fail_kill:
            raise TimeoutError("no kill confirmation")
        self.containers.pop(name, None)

    def remove(self, name):
        self.removed.append(name)
        self.containers.pop(name, None)


@pytest.fixture
def manager(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    store.create_workflow(("demo/joplin", 1), "r1", budget_limit=5_000_000)
    docker = FakeDocker()
    return WorkspaceManager(store, tmp_path / "workspaces", docker=docker,
                            server_token="local-server-key", retention_hours=24), docker


def test_ensure_persists_stable_identity_and_only_issue_storage_mount(manager):
    workspaces, docker = manager
    first = workspaces.ensure(("demo/joplin", 1), BASE, IMAGE)
    assert workspaces.ensure(("demo/joplin", 1), BASE, IMAGE) == first
    assert len(docker.runs) == 1
    spec = docker.runs[0]
    assert spec.image == "ghcr.io/openhands/agent-server@" + IMAGE
    assert spec.publish_host == "127.0.0.1"
    assert spec.server_auth_enabled is True
    assert spec.mounts == ((str(workspaces.root / first), "/workspace"),)
    assert spec.labels["dev.openhands.joplin.workspace"] == first
    assert spec.environment["OH_PERSISTENCE_DIR"] == "/workspace/.openhands"
    assert spec.environment["OH_LEASE_TTL_SECONDS"] == "0"
    assert all("docker.sock" not in str(mount) for mount in spec.mounts)
    row = workspaces.record(first)
    assert row["storage_id"] == str(workspaces.root / first)
    assert row["container_id"] == "container-1"


def test_restart_reattaches_and_container_loss_reuses_persistent_storage(manager):
    workspaces, docker = manager
    identifier = workspaces.ensure(("demo/joplin", 1), BASE, IMAGE)
    restarted = WorkspaceManager(workspaces.store, workspaces.root, docker=docker,
                                 server_token="local-server-key", retention_hours=24)
    restarted.reattach(identifier)
    assert len(docker.runs) == 1
    docker.containers.clear()
    restarted.reattach(identifier)
    assert len(docker.runs) == 2
    assert docker.runs[1].mounts == docker.runs[0].mounts
    assert restarted.record(identifier)["container_id"] == "container-2"


def test_saved_state_rejects_incompatible_image_base_and_version(manager):
    workspaces, _ = manager
    identifier = workspaces.ensure(("demo/joplin", 1), BASE, IMAGE)
    with pytest.raises(ValueError, match="base SHA"):
        workspaces.ensure(("demo/joplin", 1), "c" * 40, IMAGE)
    with pytest.raises(ValueError, match="image digest"):
        workspaces.ensure(("demo/joplin", 1), BASE, "sha256:" + "d" * 64)
    with workspaces.store.transaction() as db:
        db.execute("UPDATE workspaces SET schema_version=99 WHERE id=?", (identifier,))
    with pytest.raises(ValueError, match="state version"):
        workspaces.reattach(identifier)


def test_stop_keeps_durable_state_until_docker_confirms(manager):
    workspaces, docker = manager
    identifier = workspaces.ensure(("demo/joplin", 1), BASE, IMAGE)
    docker.fail_stop = True
    docker.fail_kill = True
    with pytest.raises(TimeoutError):
        workspaces.stop(identifier)
    assert workspaces.record(identifier)["status"] == "ready"
    docker.fail_stop = False
    docker.fail_kill = False
    workspaces.stop(identifier)
    assert workspaces.record(identifier)["status"] == "stopped"


def test_stop_forces_unresponsive_container_and_confirms_removal(manager):
    workspaces, docker = manager
    identifier = workspaces.ensure(("demo/joplin", 1), BASE, IMAGE)
    docker.fail_stop = True
    workspaces.stop(identifier)
    assert docker.inspect(docker.runs[0].name) is None
    assert workspaces.record(identifier)["status"] == "stopped"


def test_cleanup_keeps_active_failed_and_foreign_workspaces(manager):
    workspaces, docker = manager
    now = datetime.now(timezone.utc)
    for number, state, owned in ((1, "implementing", 1), (2, "needs-human", 1), (3, "completed", 0)):
        issue = ("demo/joplin", number)
        if number != 1:
            workspaces.store.create_workflow(issue, "r1", budget_limit=5_000_000)
        row = workspaces.store.workflow(issue)
        workspaces.store.cas_workflow(issue, row.version, state=state)
        identifier = f"workspace-{number}"
        with workspaces.store.transaction() as db:
            db.execute("INSERT INTO workspaces(id,repo,issue_number,status,storage_id,image_digest,base_sha,completed_at,owned) VALUES(?,?,?,?,?,?,?,?,?)",
                       (identifier, *issue, "ready", str(workspaces.root / identifier), IMAGE, BASE,
                        (now - timedelta(hours=48)).isoformat(), owned))
    assert workspaces.cleanup(now) == []
    assert docker.removed == []


def test_cleanup_removes_only_completed_owned_expired_workspace(manager):
    workspaces, docker = manager
    identifier = workspaces.ensure(("demo/joplin", 1), BASE, IMAGE)
    now = datetime.now(timezone.utc)
    row = workspaces.store.workflow(("demo/joplin", 1))
    with workspaces.store.transaction() as db:
        db.execute("UPDATE workflows SET state='completed' WHERE repo=? AND issue_number=?", row.issue)
        db.execute("UPDATE workspaces SET completed_at=? WHERE id=?",
                   ((now - timedelta(hours=25)).isoformat(), identifier))
    assert workspaces.cleanup(now) == [identifier]
    assert docker.inspect(docker.runs[0].name) is None
    assert not (workspaces.root / identifier).exists()


def test_foreign_container_with_same_name_cannot_be_reattached_or_deleted(manager):
    workspaces, docker = manager
    identifier = workspaces.ensure(("demo/joplin", 1), BASE, IMAGE)
    name = docker.runs[0].name
    docker.containers[name] = ContainerInfo("foreign", name, True, docker.runs[0].image,
                                            {"foreign": "yes"}, 8123)
    with pytest.raises(ValueError, match="ownership"):
        workspaces.reattach(identifier)
    assert docker.removed == []


def test_same_issue_in_separate_state_roots_has_distinct_container_identity(manager, tmp_path):
    first, docker = manager
    first_id = first.ensure(("demo/joplin", 1), BASE, IMAGE)
    other_root = tmp_path / "other-state"
    other_store = Store(other_root / "state.sqlite")
    other_store.create_workflow(("demo/joplin", 1), "r1", budget_limit=5_000_000)
    second = WorkspaceManager(other_store, other_root / "workspaces", docker=docker,
                              server_token="local-server-key")
    second_id = second.ensure(("demo/joplin", 1), BASE, IMAGE)
    assert second_id != first_id
    assert len(docker.runs) == 2
