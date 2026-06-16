"""Offline demo of the self-extension mechanism — no API key required.

This drives the Synthesizer directly (the part the LLM normally calls) to show the
forge → sandbox-test → register → use loop end to end. For the full agentic
experience where Claude decides what to build, run:  daedalus "your task"
"""

from daedalus.synthesis import Synthesizer
from daedalus.toolbox import Toolbox


def main() -> None:
    toolbox = Toolbox()
    toolbox.load_primitives()
    synth = Synthesizer(toolbox=toolbox, task="compute compound interest")

    print(f"Boot toolbox: {toolbox.names()}\n")

    print("Forging a tool that fails its self-test (bad formula)...")
    bad = synth.handle(
        "create_tool",
        {
            "name": "compound_interest",
            "description": "Compute compound interest.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
            # Bug: uses simple interest, so the self-test will fail.
            "python_code": "def run(principal, rate, years):\n    return str(principal * rate * years)\n",
            "test_code": "assert abs(float(run(principal=1000, rate=0.05, years=2)) - 1102.5) < 0.01",
        },
    )
    print("  ->", bad.message.splitlines()[0], "\n")

    print("Retrying with the correct formula...")
    good = synth.handle(
        "create_tool",
        {
            "name": "compound_interest",
            "description": "Compute the final value of compound interest.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "principal": {"type": "number"},
                    "rate": {"type": "number"},
                    "years": {"type": "integer"},
                },
                "required": ["principal", "rate", "years"],
            },
            "python_code": (
                "def run(principal, rate, years):\n"
                "    return str(round(principal * (1 + rate) ** years, 2))\n"
            ),
            "test_code": "assert abs(float(run(principal=1000, rate=0.05, years=2)) - 1102.5) < 0.01",
        },
    )
    print("  ->", good.message, "\n")

    print(f"Toolbox now: {toolbox.names()}")
    print("Calling the forged tool:")
    print("  compound_interest(2000, 0.07, 10) =", toolbox.call("compound_interest", principal=2000, rate=0.07, years=10))


if __name__ == "__main__":
    main()
