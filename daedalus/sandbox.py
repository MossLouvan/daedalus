"""Isolated execution of a freshly synthesized tool's self-test.

This runs model-written code in a separate Python process with a timeout. It is
NOT a security sandbox — it bounds runtime, not capability. Run Daedalus inside a
container or disposable VM if you do not trust the model output. See README.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import SANDBOX_TIMEOUT

# Harness wrapping the candidate tool + its test. The test body executes after
# the tool's `run` is defined; printing the marker proves it reached the end.
_HARNESS = '''\
# --- candidate tool code ---
{tool_code}

# --- self-test ---
def __daedalus_test():
{indented_test}

if __name__ == "__main__":
    __daedalus_test()
    print("__DAEDALUS_TEST_PASSED__")
'''


@dataclass
class TestResult:
    ok: bool
    output: str


def _indent(code: str, spaces: int = 4) -> str:
    pad = " " * spaces
    lines = code.splitlines() or ["pass"]
    return "\n".join(pad + line if line.strip() else line for line in lines)


def run_self_test(tool_code: str, test_code: str, timeout: int | None = None) -> TestResult:
    """Execute tool_code + test_code in a subprocess. Pass == clean exit + marker."""
    timeout = timeout or SANDBOX_TIMEOUT
    program = _HARNESS.format(tool_code=tool_code, indented_test=_indent(test_code))

    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "candidate.py"
        script.write_text(program, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,  # run in a scratch dir so test artifacts don't pollute the repo
            )
        except subprocess.TimeoutExpired:
            return TestResult(False, f"Test timed out after {timeout}s.")

    combined = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0 and "__DAEDALUS_TEST_PASSED__" in proc.stdout:
        return TestResult(True, combined)
    return TestResult(False, combined or f"Process exited with code {proc.returncode}.")
