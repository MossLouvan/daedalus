"""Provider-agnostic LLM layer.

Daedalus's agent loop speaks a single neutral message format. Each backend here
translates that format to/from its provider's native tool-calling shape, so the
same agent runs on Anthropic Claude, OpenAI, or any OpenAI-compatible server
(Ollama, OpenRouter, Together, Groq, vLLM, LM Studio, …).

Neutral message format (what agent.py builds):
    {"role": "user", "content": "<text>"}
    {"role": "assistant", "text": "<text>", "tool_calls": [ToolCall, ...]}
    {"role": "tool", "results": [{"id", "name", "content"}, ...]}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import config

# Sensible default model per provider. Override with DAEDALUS_MODEL or --model.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
    "ollama": "qwen2.5-coder:7b",  # a capable, tool-calling open-source default
}

# Aliases that map onto the OpenAI-compatible backend.
_OPENAI_COMPATIBLE = {"openai", "ollama", "openai-compatible", "local"}


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Completion:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end"  # "tool_use" when the model wants tools run


# --------------------------------------------------------------------------- #
# Neutral <-> Anthropic
# --------------------------------------------------------------------------- #
def to_anthropic_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            content: list[dict] = []
            if m.get("text"):
                content.append({"type": "text", "text": m["text"]})
            for tc in m.get("tool_calls", []):
                content.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
                )
            out.append({"role": "assistant", "content": content})
        elif m["role"] == "tool":
            content = [
                {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
                for r in m["results"]
            ]
            out.append({"role": "user", "content": content})
    return out


def parse_anthropic_response(response) -> Completion:
    text_parts, calls = [], []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, input=block.input or {}))
    stop = "tool_use" if response.stop_reason == "tool_use" else "end"
    return Completion("".join(text_parts), calls, stop)


# --------------------------------------------------------------------------- #
# Neutral <-> OpenAI (and any OpenAI-compatible server)
# --------------------------------------------------------------------------- #
def to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            msg: dict = {"role": "assistant", "content": m.get("text") or None}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.input)},
                    }
                    for tc in m["tool_calls"]
                ]
            out.append(msg)
        elif m["role"] == "tool":
            for r in m["results"]:
                out.append({"role": "tool", "tool_call_id": r["id"], "content": r["content"]})
    return out


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def extract_text_tool_calls(text: str) -> list[ToolCall]:
    """Fallback for weaker models that emit a tool call as JSON in their text
    (e.g. ```json {"name": "x", "arguments": {...}}```) instead of using the
    structured tool_calls field. Conservative: only fires on a single clean
    JSON object carrying a name plus arguments/parameters.
    """
    if not text:
        return []
    s = text.strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        return []
    try:
        obj = json.loads(s[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(obj, dict):
        return []
    name = obj.get("name")
    args = obj.get("arguments", obj.get("parameters", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return []
    if isinstance(name, str) and isinstance(args, dict):
        return [ToolCall(id="text_call_0", name=name, input=args)]
    return []


def parse_openai_response(response) -> Completion:
    choice = response.choices[0]
    msg = choice.message
    calls = []
    for tc in (msg.tool_calls or []):
        raw = tc.function.arguments
        try:
            args = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))

    text = msg.content or ""
    if not calls:  # weak-model fallback: maybe the call is buried in the text
        calls = extract_text_tool_calls(text)

    stop = "tool_use" if (choice.finish_reason == "tool_calls" or calls) else "end"
    return Completion(text, calls, stop)


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #
class AnthropicClient:
    def __init__(self, model: str, max_tokens: int) -> None:
        import anthropic  # lazy: only required when this provider is used

        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    def describe(self) -> str:
        return f"anthropic · {self.model}"

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> Completion:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=tools,
            messages=to_anthropic_messages(messages),
        )
        return parse_anthropic_response(response)


class OpenAIClient:
    """Works against OpenAI and any OpenAI-compatible endpoint (Ollama, OpenRouter…)."""

    def __init__(self, model: str, max_tokens: int, base_url: str, api_key: str, label: str) -> None:
        try:
            import openai  # lazy import
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "OpenAI-compatible providers need the 'openai' package: pip install openai"
            ) from exc

        self.model = model
        self.max_tokens = max_tokens
        self._label = label
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)

    def describe(self) -> str:
        return f"{self._label} · {self.model}"

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> Completion:
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            tools=to_openai_tools(tools),
            tool_choice="auto",
            messages=to_openai_messages(system, messages),
        )
        return parse_openai_response(response)


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def resolve_model(provider: str, explicit: str | None) -> str:
    return explicit or config.MODEL_OVERRIDE or DEFAULT_MODELS.get(provider, DEFAULT_MODELS["openai"])


def build_client(provider: str | None = None, model: str | None = None):
    """Construct the right client from explicit args, then env/config defaults."""
    provider = (provider or config.PROVIDER).lower()
    chosen_model = resolve_model(provider, model)

    if provider == "anthropic":
        return AnthropicClient(chosen_model, config.MAX_TOKENS)

    if provider in _OPENAI_COMPATIBLE:
        if provider == "ollama":
            base_url = config.OPENAI_BASE_URL or "http://localhost:11434/v1"
            api_key = config.OPENAI_API_KEY or "ollama"  # Ollama ignores the key
            label = "ollama"
        else:
            base_url = config.OPENAI_BASE_URL or "https://api.openai.com/v1"
            api_key = config.OPENAI_API_KEY or "missing-key"
            label = "openai-compatible"
        return OpenAIClient(chosen_model, config.MAX_TOKENS, base_url, api_key, label)

    raise ValueError(
        f"Unknown provider {provider!r}. Use 'anthropic', 'openai', or 'ollama' "
        f"(or set OPENAI_BASE_URL for any OpenAI-compatible server)."
    )
