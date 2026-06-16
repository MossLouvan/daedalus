from daedalus.sandbox import run_self_test


def test_passing_tool():
    tool = "def run(a, b):\n    return str(a + b)\n"
    test = "assert run(a=2, b=3) == '5'"
    result = run_self_test(tool, test)
    assert result.ok, result.output


def test_failing_assertion_is_caught():
    tool = "def run(a, b):\n    return str(a + b)\n"
    test = "assert run(a=2, b=3) == '6'"  # wrong
    result = run_self_test(tool, test)
    assert not result.ok
    assert "AssertionError" in result.output


def test_syntax_error_is_caught():
    result = run_self_test("def run(:\n    pass", "assert True")
    assert not result.ok


def test_timeout_is_enforced():
    tool = "def run():\n    while True:\n        pass\n"
    test = "run()"
    result = run_self_test(tool, test, timeout=2)
    assert not result.ok
    assert "timed out" in result.output.lower()
