"""The dynamic tool registry.

The toolbox holds both primitive tools and synthesized tools, exposes their
schemas to the Claude API, and can register a brand-new tool from a file at
runtime so a freshly forged tool is usable on the very next turn.
"""

from __future__ import annotations

import importlib.util
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import primitives
from .config import GENERATED_DIR


@dataclass
class Tool:
    schema: dict
    fn: Callable[..., str]
    source: str  # "primitive" or "generated"
    path: str | None = None

    @property
    def name(self) -> str:
        return self.schema["name"]


def _import_module_from_path(path: Path):
    """Import a standalone .py file under a unique module name (no caching collisions)."""
    mod_name = f"daedalus_tool_{path.stem}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Toolbox:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self.load_errors: list[str] = []

    # -- loading -----------------------------------------------------------
    def load_primitives(self) -> None:
        for schema, fn in primitives.all_primitives():
            self._tools[schema["name"]] = Tool(schema=schema, fn=fn, source="primitive")

    def load_generated(self) -> None:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        for path in sorted(GENERATED_DIR.glob("*.py")):
            try:
                self.register_from_file(path)
            except Exception as exc:  # a broken saved tool must not crash startup
                self.load_errors.append(f"{path.name}: {exc}")

    def register_from_file(self, path: Path) -> str:
        module = _import_module_from_path(path)
        schema = getattr(module, "SCHEMA", None)
        fn = getattr(module, "run", None)
        if not isinstance(schema, dict) or not callable(fn):
            raise ValueError("tool module must define SCHEMA (dict) and run(**kwargs)")
        name = schema["name"]
        self._tools[name] = Tool(schema=schema, fn=fn, source="generated", path=str(path))
        return name

    # -- access ------------------------------------------------------------
    def specs(self) -> list[dict]:
        """Tool schemas in the shape the Claude API expects."""
        return [t.schema for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def call(self, name: str, **kwargs) -> str:
        result = self._tools[name].fn(**kwargs)
        return result if isinstance(result, str) else str(result)

    def names(self) -> list[str]:
        return list(self._tools)

    def generated(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.source == "generated"]
