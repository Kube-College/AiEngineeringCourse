"""The Joplin runtime image must be pinned to validated local build output."""

import json
import re
from pathlib import Path

import pytest


BASE_SHA = "1d6beb0443e6d958b2c241f45978bd5de069f309"
MANIFEST = Path(__file__).resolve().parents[1] / "docker" / "versions.json"


@pytest.fixture
def manifest():
    return json.loads(MANIFEST.read_text())


def test_manifest_pins_baseline_and_image(manifest):
    assert manifest["joplin_sha"] == BASE_SHA
    assert re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", manifest["base_image_digest"])
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", manifest["built_image_digest"])


def test_manifest_has_qualified_toolchain(manifest):
    assert manifest["agent_server_version"] == "1.48.0"
    assert re.fullmatch(r"3\.\d+\.\d+", manifest["python_version"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["node_version"])
    assert tuple(map(int, manifest["node_version"].split("."))) >= (22, 19, 0)
    assert manifest["package_manager"] == "yarn@4.16.0"
