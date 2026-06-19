"""Provider-agnostic conversion tests — pure, no network or API key needed."""

import json
from types import SimpleNamespace

from daedalus import llm
from daedalus.llm import (
    Completion,
    ToolCall,
    extract_text_tool_calls,
    parse_anthropic_response,
    parse_openai_response,
    resolve_model,
    to_anthropic_messages,
    to_openai_messages,
    to_openai_tools,
)

NEUTRAL = [
    {"role": "user", "content": "do it"},
    {
        "role": "assistant",
        "text": "calling a tool",
        "tool_calls": [ToolCall(id="t1", name="add", input={"a": 1, "b": 2})],
    },
    {"role": "tool", "results": [{"id": "t1", "name": "add", "content": "3"}]},
]

TOOLS = [{"name": "add", "description": "add", "input_schema": {"type": "object", "properties": {}}}]


def test_anthropic_message_shapes():
    out = to_anthropic_messages(NEUTRAL)
    assert out[0] == {"role": "user", "content": "do it"}
    # assistant turn carries a tool_use block
    assert out[1]["role"] == "assistant"
    assert any(b["type"] == "tool_use" and b["id"] == "t1" for b in out[1]["content"])
    # tool results become a user message with tool_result blocks
    assert out[2]["role"] == "user"
    assert out[2]["content"][0]["tool_use_id"] == "t1"


def test_openai_message_shapes():
    out = to_openai_messages("SYS", NEUTRAL)
    assert out[0] == {"role": "system", "content": "SYS"}
    assistant = out[2]
    assert assistant["role"] == "assistant"
    call = assistant["tool_calls"][0]
    assert call["id"] == "t1"
    assert json.loads(call["function"]["arguments"]) == {"a": 1, "b": 2}
    tool_msg = out[3]
    assert tool_msg == {"role": "tool", "tool_call_id": "t1", "content": "3"}


def test_openai_tools_wrapping():
    out = to_openai_tools(TOOLS)
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "add"
    assert out[0]["function"]["parameters"] == TOOLS[0]["input_schema"]


def test_parse_anthropic_response():
    resp = SimpleNamespace(
        stop_reason="tool_use",
        content=[
            SimpleNamespace(type="text", text="hi"),
            SimpleNamespace(type="tool_use", id="x", name="add", input={"a": 1}),
        ],
    )
    result = parse_anthropic_response(resp)
    assert isinstance(result, Completion)
    assert result.text == "hi"
    assert result.stop_reason == "tool_use"
    assert result.tool_calls[0].name == "add"


def test_parse_openai_response_with_bad_json_args():
    tc = SimpleNamespace(id="x", function=SimpleNamespace(name="add", arguments="{not json"))
    resp = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="tool_calls", message=SimpleNamespace(content=None, tool_calls=[tc]))]
    )
    result = parse_openai_response(resp)
    assert result.tool_calls[0].input == {}  # malformed args degrade to empty dict
    assert result.stop_reason == "tool_use"


def test_text_tool_call_fallback_fenced():
    # qwen-style: tool call emitted as a fenced JSON block in the text
    text = '```json\n{"name": "compute_factorial", "arguments": {"n": 12}}\n```'
    calls = extract_text_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "compute_factorial"
    assert calls[0].input == {"n": 12}


def test_text_tool_call_fallback_parameters_key():
    # llama-style: uses "parameters" instead of "arguments"
    calls = extract_text_tool_calls('{"name": "add", "parameters": {"a": 1}}')
    assert calls[0].input == {"a": 1}


def test_text_tool_call_fallback_ignores_plain_prose():
    assert extract_text_tool_calls("The answer is 479001600.") == []
    assert extract_text_tool_calls('{"just": "data"}') == []  # no name/args


def test_parse_openai_response_uses_text_fallback():
    msg = SimpleNamespace(content='{"name": "add", "arguments": {"a": 2}}', tool_calls=[])
    resp = SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=msg)])
    result = parse_openai_response(resp)
    assert result.stop_reason == "tool_use"
    assert result.tool_calls[0].name == "add"


def test_resolve_model_precedence(monkeypatch):
    monkeypatch.setattr(llm.config, "MODEL_OVERRIDE", None)
    assert resolve_model("ollama", None) == llm.DEFAULT_MODELS["ollama"]
    assert resolve_model("ollama", "custom:latest") == "custom:latest"
    monkeypatch.setattr(llm.config, "MODEL_OVERRIDE", "env-model")
    assert resolve_model("anthropic", None) == "env-model"
