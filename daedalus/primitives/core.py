"""The three primitive filesystem tools Daedalus boots with.

Each primitive follows the same contract as a synthesized tool:
a ``SCHEMA`` dict and a ``run(**kwargs) -> str`` callable. Keeping the contract
uniform means the toolbox treats built-in and forged tools identically.
"""

from __future__ import annotations

import os
from pathlib import Path

# Cap how much file content we ever return, so a giant file cannot blow the
# context window in a single tool result.
_MAX_READ_CHARS = 20_000


def read_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.is_file():
        return f"ERROR: no such file: {path}"
    text = p.read_text(encoding="utf-8", errors="replace")
    if len(text) > _MAX_READ_CHARS:
        return text[:_MAX_READ_CHARS] + f"\n... [truncated, {len(text)} chars total]"
    return text


def write_file(path: str, content: str) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {path}"


def list_dir(path: str = ".") -> str:
    p = Path(path).expanduser()
    if not p.is_dir():
        return f"ERROR: not a directory: {path}"
    entries = []
    for name in sorted(os.listdir(p)):
        full = p / name
        entries.append(f"{'dir ' if full.is_dir() else 'file'}  {name}")
    return "\n".join(entries) if entries else "(empty directory)"


PRIMITIVES = [
    (
        {
            "name": "read_file",
            "description": "Read a UTF-8 text file and return its contents (truncated if very large).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to read."}
                },
                "required": ["path"],
            },
        },
        read_file,
    ),
    (
        {
            "name": "write_file",
            "description": "Write text to a file, creating parent directories as needed. Overwrites existing files.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination file path."},
                    "content": {"type": "string", "description": "Text to write."},
                },
                "required": ["path", "content"],
            },
        },
        write_file,
    ),
    (
        {
            "name": "list_dir",
            "description": "List the entries of a directory.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default '.')."}
                },
                "required": [],
            },
        },
        list_dir,
    ),
]
