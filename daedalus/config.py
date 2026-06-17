"""Runtime configuration, sourced from environment variables with sane defaults."""

from __future__ import annotations

import os
from pathlib import Path

# Which LLM backend to use: "anthropic", "openai", or "ollama" (and any other
# OpenAI-compatible server via OPENAI_BASE_URL). Defaults to Anthropic.
PROVIDER = os.environ.get("DAEDALUS_PROVIDER", "anthropic").lower()

# Universal model override. Falls back to ANTHROPIC_MODEL for back-compat, then
# to the per-provider default in llm.DEFAULT_MODELS.
MODEL_OVERRIDE = os.environ.get("DAEDALUS_MODEL") or os.environ.get("ANTHROPIC_MODEL")

# OpenAI-compatible connection settings (used by the openai/ollama backends).
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Per-call output cap.
MAX_TOKENS = int(os.environ.get("DAEDALUS_MAX_TOKENS", "4096"))

# Hard ceiling on agent loop iterations, so a confused run cannot bill forever.
MAX_ITERATIONS = int(os.environ.get("DAEDALUS_MAX_ITERATIONS", "40"))

# Seconds a freshly synthesized tool's self-test may run before it is killed.
SANDBOX_TIMEOUT = int(os.environ.get("DAEDALUS_SANDBOX_TIMEOUT", "15"))

# Where synthesized tools and their manifest live. Defaults to ./tools_generated
# relative to wherever Daedalus is invoked, so each project keeps its own toolbox.
GENERATED_DIR = Path(
    os.environ.get("DAEDALUS_TOOLS_DIR", Path.cwd() / "tools_generated")
).resolve()

MANIFEST_PATH = GENERATED_DIR / "manifest.json"
