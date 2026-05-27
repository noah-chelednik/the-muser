"""The Muser CLI entry point.

Interactive composition session using Click and Rich for a
polished terminal experience.
"""

import logging
import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from src.orchestrator.agent import run_agent_turn
from src.orchestrator.composition_state import CompositionState
from src.orchestrator.config import COMPOSITIONS_DIR
from src.orchestrator.session_logger import SessionLogger

console = Console()
logger = logging.getLogger("muser")


@click.command()
@click.option(
    "--composition",
    "-c",
    default=None,
    help="Name of an existing composition to resume.",
)
@click.option(
    "--model",
    "-m",
    default=None,
    help="LLM model to use (e.g., 'ollama_chat/qwen3:30b-a3b', overrides provider chain).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging.",
)
@click.option(
    "--stream/--no-stream",
    default=True,
    help="Stream LLM responses token-by-token (default: enabled).",
)
def main(composition: str | None, model: str | None, verbose: bool, stream: bool) -> None:
    """The Muser — Natural language music composition."""
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    console.print(
        Panel(
            "[bold]The Muser[/bold] — Natural Language Music Composition\n"
            "Type your instructions to compose music. Type [bold]quit[/bold] to exit.",
            title="Welcome",
            border_style="blue",
        )
    )

    # Initialize composition state
    state = CompositionState()
    if composition:
        plan_path = COMPOSITIONS_DIR / composition / "plan.json"
        if plan_path.exists():
            state.load_plan(str(plan_path))
            state.project_dir = str(COMPOSITIONS_DIR / composition)
            console.print(
                f"[green]Resumed composition:[/green] {state.project.get('title', composition)}"
            )
        else:
            console.print(
                f"[yellow]No existing composition found at {plan_path}. Starting fresh.[/yellow]"
            )
            state.project["title"] = composition
            state.project_dir = str(COMPOSITIONS_DIR / composition)

    conversation_history: list[dict] = []
    session_logger = SessionLogger()

    while True:
        try:
            user_input = console.input("\n[bold blue]You:[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() == "status":
            context = state.to_context_string()
            console.print(Markdown(context))
            continue

        if user_input.lower() == "sections":
            sections = state.list_sections()
            if not sections:
                console.print("[dim]No sections yet.[/dim]")
            else:
                for s in sections:
                    status_icon = (
                        "[green]done[/green]" if s["has_file"] else "[yellow]pending[/yellow]"
                    )
                    console.print(f"  {status_icon} {s['name']}")
            continue

        # Run agent turn
        if stream:
            _streaming_first_token = True

            def _print_token(token: str) -> None:
                nonlocal _streaming_first_token
                if _streaming_first_token:
                    console.print()
                    _streaming_first_token = False
                console.print(token, end="", highlight=False)

            response = run_agent_turn(
                user_message=user_input,
                conversation_history=conversation_history,
                composition_state=state,
                model=model,
                session_logger=session_logger,
                on_token=_print_token,
            )
            if not _streaming_first_token:
                console.print()
            else:
                console.print()
                console.print(Markdown(response))
        else:
            with console.status("[bold green]Composing...[/bold green]"):
                response = run_agent_turn(
                    user_message=user_input,
                    conversation_history=conversation_history,
                    composition_state=state,
                    model=model,
                    session_logger=session_logger,
                )
            console.print()
            console.print(Markdown(response))


if __name__ == "__main__":
    main()
