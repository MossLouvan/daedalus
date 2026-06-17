"""Command-line interface for Daedalus."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .config import MANIFEST_PATH, PROVIDER
from .toolbox import Toolbox

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table

    _RICH = True
except ImportError:  # graceful fallback if rich isn't installed
    _RICH = False


def _build_toolbox() -> Toolbox:
    tb = Toolbox()
    tb.load_primitives()
    tb.load_generated()
    return tb


class RichReporter:
    """Pretty live output of the agent's reasoning, tool calls, and tool forging."""

    def __init__(self) -> None:
        self.console = Console()

    def on_iteration(self, n: int) -> None:
        self.console.rule(f"[dim]step {n}[/dim]", style="dim")

    def on_assistant_text(self, text: str) -> None:
        self.console.print(Panel(text.strip(), title="daedalus", border_style="cyan"))

    def on_tool_call(self, name, payload, is_meta) -> None:
        tag = "[magenta]forge[/magenta]" if is_meta else "[green]tool[/green]"
        if name == "create_tool":
            self.console.print(f"{tag} [bold]create_tool[/bold] → {payload.get('name', '?')}")
            self.console.print(
                Syntax(payload.get("python_code", ""), "python", theme="ansi_dark", word_wrap=True)
            )
        else:
            args = ", ".join(f"{k}={_short(v)}" for k, v in payload.items())
            self.console.print(f"{tag} [bold]{name}[/bold]({args})")

    def on_tool_result(self, name, result) -> None:
        self.console.print(f"  [dim]↳ {_short(result, 300)}[/dim]")

    def on_tool_created(self, name) -> None:
        self.console.print(f"  [bold magenta]✦ forged new tool: {name}[/bold magenta]")


def _short(value, limit: int = 80) -> str:
    s = str(value).replace("\n", " ")
    return s if len(s) <= limit else s[:limit] + "…"


def _plain_print(*args):
    print(*args, file=sys.stderr, flush=True)


def cmd_run(args) -> int:
    from .agent import Agent

    task = args.task
    if args.task_file:
        with open(args.task_file, encoding="utf-8") as f:
            task = f.read().strip()
    if not task:
        _plain_print("error: provide a task string or --task-file")
        return 2

    toolbox = _build_toolbox()
    reporter = RichReporter() if (_RICH and not args.no_color) else None

    try:
        agent = Agent(
            toolbox=toolbox, reporter=reporter, provider=args.provider, model=args.model
        )
    except Exception as exc:  # missing key, missing package, bad provider, etc.
        _plain_print(f"failed to init LLM client: {type(exc).__name__}: {exc}")
        _plain_print(
            "check your provider/credentials — e.g. ANTHROPIC_API_KEY, or "
            "DAEDALUS_PROVIDER=ollama for a local model."
        )
        return 1

    if reporter:
        reporter.console.print(f"[dim]using {agent.client.describe()}[/dim]")
    else:
        _plain_print(f"using {agent.client.describe()}")

    try:
        final = agent.run(task)
    except Exception as exc:  # connection refused, auth, rate limit, etc.
        _plain_print(f"\nrun failed: {type(exc).__name__}: {exc}")
        if "Connection" in type(exc).__name__:
            _plain_print("is your model server running? (e.g. `ollama serve`)")
        return 1

    if _RICH and not args.no_color:
        Console().print(Panel(final.strip() or "(no text)", title="result", border_style="green"))
    else:
        print("\n=== RESULT ===\n" + final)
    return 0


def cmd_tools(args) -> int:
    toolbox = _build_toolbox()
    generated = toolbox.generated()

    if _RICH:
        console = Console()
        table = Table(title="Daedalus toolbox", show_lines=False)
        table.add_column("tool", style="bold")
        table.add_column("kind")
        table.add_column("description")
        for spec in toolbox.specs():
            kind = "forged" if toolbox.get(spec["name"]).source == "generated" else "primitive"
            style = "magenta" if kind == "forged" else "dim"
            table.add_row(spec["name"], f"[{style}]{kind}[/{style}]", spec["description"])
        console.print(table)
        console.print(f"\n[bold]{len(generated)}[/bold] tools forged so far.")
    else:
        for spec in toolbox.specs():
            print(f"{spec['name']}: {spec['description']}")
    return 0


def cmd_history(args) -> int:
    if not MANIFEST_PATH.is_file():
        print("No tools forged yet.")
        return 0
    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for e in entries:
        print(f"[{e.get('created_at', '?')}] {e['name']} — {e['description']}")
        if e.get("task"):
            print(f"    task: {_short(e['task'], 100)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="daedalus",
        description="A self-extending LLM agent that forges its own tools.",
    )
    p.add_argument("--version", action="version", version=f"daedalus {__version__}")
    sub = p.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run the agent on a task (default command)")
    run.add_argument("task", nargs="?", default="", help="the task to perform")
    run.add_argument("--task-file", help="read the task from a file")
    run.add_argument(
        "--provider",
        help=f"anthropic | openai | ollama (default: {PROVIDER}; or set DAEDALUS_PROVIDER)",
    )
    run.add_argument("--model", help="override the model id")
    run.add_argument("--no-color", action="store_true", help="plain output")
    run.set_defaults(func=cmd_run)

    tools = sub.add_parser("tools", help="list the current toolbox")
    tools.set_defaults(func=cmd_tools)

    hist = sub.add_parser("history", help="show the log of every tool ever forged")
    hist.set_defaults(func=cmd_history)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()

    # Allow `daedalus "do a thing"` as shorthand for `daedalus run "do a thing"`.
    if argv and argv[0] not in {"run", "tools", "history", "-h", "--help", "--version"}:
        argv = ["run", *argv]

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
