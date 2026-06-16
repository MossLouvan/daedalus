import json

import pytest

from daedalus import synthesis
from daedalus.synthesis import Synthesizer
from daedalus.toolbox import Toolbox


@pytest.fixture
def synth(tmp_path, monkeypatch):
    """A synthesizer whose generated tools land in a temp dir."""
    monkeypatch.setattr(synthesis, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(synthesis, "MANIFEST_PATH", tmp_path / "manifest.json")
    tb = Toolbox()
    tb.load_primitives()
    return Synthesizer(toolbox=tb, task="demo task")


def _payload(**over):
    base = {
        "name": "add",
        "description": "Add two integers.",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
        "python_code": "def run(a, b):\n    return str(a + b)\n",
        "test_code": "assert run(a=2, b=2) == '4'",
    }
    base.update(over)
    return base


def test_create_tool_persists_and_registers(synth, tmp_path):
    result = synth.handle("create_tool", _payload())
    assert result.created_tool == "add"
    assert synth.toolbox.has("add")
    assert synth.toolbox.call("add", a=10, b=5) == "15"  # usable immediately
    assert (tmp_path / "add.py").is_file()

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest[0]["name"] == "add"
    assert manifest[0]["task"] == "demo task"


def test_failing_self_test_is_not_saved(synth, tmp_path):
    result = synth.handle("create_tool", _payload(test_code="assert run(a=2, b=2) == '5'"))
    assert result.created_tool is None
    assert not synth.toolbox.has("add")
    assert not (tmp_path / "add.py").exists()
    assert "FAILED" in result.message


def test_invalid_identifier_rejected(synth):
    result = synth.handle("create_tool", _payload(name="2bad"))
    assert result.created_tool is None
    assert "identifier" in result.message


def test_duplicate_name_rejected(synth):
    synth.handle("create_tool", _payload())
    result = synth.handle("create_tool", _payload())
    assert result.created_tool is None
    assert "already exists" in result.message


def test_list_tools_includes_primitives(synth):
    result = synth.handle("list_tools", {})
    assert "read_file" in result.message
