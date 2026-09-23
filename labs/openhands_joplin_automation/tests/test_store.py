from dataclasses import replace

import pytest

from openhands_controller.contracts import EventConflict
from openhands_controller.contracts import VersionConflict
from openhands_controller.config import Config
from openhands_controller.store import Store
from support import Harness


def test_event_replay_and_conflict(tmp_path):
    h = Harness(tmp_path)
    event = h.issue()
    assert h.store.record_event(event) is True
    assert h.store.record_event(event) is False
    with pytest.raises(EventConflict):
        h.store.record_event(replace(event, payload={"title": "changed"}))


def test_workflow_survives_restart_and_stale_writer_is_rejected(tmp_path):
    h = Harness(tmp_path)
    assert h.store.create_workflow(("demo/joplin", 1), "r1")
    stale = Store(tmp_path / "state.sqlite")
    original = stale.workflow(("demo/joplin", 1))
    h.store.cas_workflow(("demo/joplin", 1), original["version"], state="triaging")
    with pytest.raises(VersionConflict):
        stale.cas_workflow(("demo/joplin", 1), original["version"], state="cancelled")
    h.restart()
    assert h.store.workflow(("demo/joplin", 1))["state"] == "triaging"


@pytest.mark.parametrize("values", [{"poll_seconds": 0}, {"max_active": 2}, {"unknown": 1}])
def test_invalid_config_is_rejected(values):
    with pytest.raises(ValueError):
        Config.from_mapping(values)
