"""The core agentic loop.

Daedalus is a standard Claude tool-use loop with one twist: alongside its normal
tools it carries the `create_tool` meta-tool, so it can grow its own toolbox
mid-task and immediately use what it forged.
"""

from __future__ import annotations

import json
from typing import Protocol

import anthropic

from .config import MAX_ITERATIONS, MAX_TOKENS, MODEL
from .prompts import SYSTEM_PROMPT
from .synthesis import Synthesizer
from .toolbox import Toolbox


class Reporter(Protocol):
    """UI hook surface. The CLI implements this with rich; tests use the null one."""

    def on_assistant_text(self, text: str) -> None: ...
    def on_tool_call(self, name: str, payload: dict, is_meta: bool) -> None: ...
    def on_tool_result(self, name: str, result: str) -> None: ...
    def on_tool_created(self, name: str) -> None: ...
    def on_iteration(self, n: int) -> None: ...


class NullReporter:
    def on_assistant_text(self, text: str) -> None: ...
    def on_tool_call(self, name: str, payload: dict, is_meta: bool) -> None: ...
    def on_tool_result(self, name: str, result: str) -> None: ...
    def on_tool_created(self, name: str) -> None: ...
    def on_iteration(self, n: int) -> None: ...


class Agent:
    def __init__(
        self,
        toolbox: Toolbox,
        reporter: Reporter | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.toolbox = toolbox
        self.reporter = reporter or NullReporter()
        self.client = client or anthropic.Anthropic()

    def _dispatch(self, synth: Synthesizer, name: str, payload: dict) -> str:
        """Route a tool call to the synthesizer (meta) or the toolbox (regular)."""
        if synth.is_meta(name):
            result = synth.handle(name, payload)
            if result.created_tool:
                self.reporter.on_tool_created(result.created_tool)
            return result.message
        if not self.toolbox.has(name):
            return f"ERROR: no tool named {name!r}."
        try:
            return self.toolbox.call(name, **payload)
        except Exception as exc:  # surface tool crashes to the model instead of dying
            return f"ERROR while running {name}: {type(exc).__name__}: {exc}"

    def run(self, task: str) -> str:
        synth = Synthesizer(toolbox=self.toolbox, task=task)
        messages: list[dict] = [{"role": "user", "content": task}]
        final_text = ""

        for i in range(1, MAX_ITERATIONS + 1):
            self.reporter.on_iteration(i)

            # Tool list is recomputed each turn so newly forged tools appear.
            tools = self.toolbox.specs() + synth.META_TOOLS
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

            tool_results = []
            for block in response.content:
                if block.type == "text":
                    final_text = block.text
                    if block.text.strip():
                        self.reporter.on_assistant_text(block.text)
                elif block.type == "tool_use":
                    payload = block.input or {}
                    self.reporter.on_tool_call(block.name, payload, synth.is_meta(block.name))
                    result = self._dispatch(synth, block.name, payload)
                    self.reporter.on_tool_result(block.name, result)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return final_text  # natural end of turn — task done

            messages.append({"role": "user", "content": tool_results})

        return final_text or "(stopped: hit the iteration limit before finishing)"
