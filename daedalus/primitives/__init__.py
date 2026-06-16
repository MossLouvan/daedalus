"""Built-in primitive tools — the irreducible substrate Daedalus starts with.

Everything computational (parsing, math, web access, transforms) is deliberately
*not* provided here. The agent must forge those tools itself. Primitives only
cover the filesystem substrate that synthesized tools build upon.
"""

from __future__ import annotations

from . import core


def all_primitives():
    """Yield (schema, callable) pairs for every primitive tool."""
    return core.PRIMITIVES
