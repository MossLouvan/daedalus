"""The core agentic loop.

Daedalus is a standard tool-use loop with one twist: alongside its normal tools it
carries the `create_tool` meta-tool, so it can grow its own toolbox mid-task and
immediately use what it forged. The loop is provider-agnostic — it talks to any
backend in :mod:`daedalus.llm` through a neutral message format.
"""

from __future__ import annotations

from typing import Protocol

from .config import MAX_ITERATIONS
from .llm import Completion, build_client
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
        client=None,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.toolbox = toolbox
        self.reporter = reporter or NullReporter()
        self.client = client or build_client(provider=provider, model=model)

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
            completion: Completion = self.client.complete(SYSTEM_PROMPT, tools, messages)

            final_text = completion.text
            if completion.text.strip():
                self.reporter.on_assistant_text(completion.text)

            # Record the assistant turn in the neutral history.
            assistant_turn: dict = {"role": "assistant"}
            if completion.text:
                assistant_turn["text"] = completion.text
            if completion.tool_calls:
                assistant_turn["tool_calls"] = completion.tool_calls
            messages.append(assistant_turn)

            if not completion.tool_calls:
                return final_text  # natural end of turn — task done

            results = []
            for tc in completion.tool_calls:
                self.reporter.on_tool_call(tc.name, tc.input, synth.is_meta(tc.name))
                result = self._dispatch(synth, tc.name, tc.input)
                self.reporter.on_tool_result(tc.name, result)
                results.append({"id": tc.id, "name": tc.name, "content": result})

            messages.append({"role": "tool", "results": results})

        return final_text or "(stopped: hit the iteration limit before finishing)"
