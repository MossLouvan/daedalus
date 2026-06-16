"""Runtime configuration, sourced from environment variables with sane defaults."""

from __future__ import annotations

import os
from pathlib import Path

# Model used for the agent loop. Sonnet 4.6 is the default because Daedalus
# spends most of its time writing and debugging Python tools.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

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
