from daedalus.toolbox import Toolbox


def test_primitives_load():
    tb = Toolbox()
    tb.load_primitives()
    names = tb.names()
    assert {"read_file", "write_file", "list_dir"} <= set(names)
    assert all("name" in spec for spec in tb.specs())


def test_read_write_roundtrip(tmp_path):
    tb = Toolbox()
    tb.load_primitives()
    target = tmp_path / "note.txt"
    tb.call("write_file", path=str(target), content="hello")
    assert tb.call("read_file", path=str(target)) == "hello"


def test_register_tool_from_file(tmp_path):
    tool_path = tmp_path / "shout.py"
    tool_path.write_text(
        'SCHEMA = {"name": "shout", "description": "upper", '
        '"input_schema": {"type": "object", "properties": {}, "required": []}}\n'
        "def run(text):\n    return text.upper()\n"
    )
    tb = Toolbox()
    name = tb.register_from_file(tool_path)
    assert name == "shout"
    assert tb.has("shout")
    assert tb.call("shout", text="hi") == "HI"
    assert tb.get("shout").source == "generated"


def test_invalid_tool_file_rejected(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("x = 1\n")  # no SCHEMA / run
    tb = Toolbox()
    try:
        tb.register_from_file(bad)
        assert False, "should have raised"
    except ValueError:
        pass
