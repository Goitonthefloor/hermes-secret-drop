"""Secret drop plugin: store a secret on the gateway host, never in the chat."""

from __future__ import annotations

from pathlib import Path

try:
    from .secret_drop import reload_secret_redactions, run_secret_command
except ImportError:  # loaded as a loose module rather than a package
    from secret_drop import reload_secret_redactions, run_secret_command


def register(ctx) -> None:
    ctx.register_command(
        "secret",
        run_secret_command,
        description="Store a secret as an environment variable without showing it to the model",
        args_hint="[NAME]",
    )

    def _on_session_start(**_kwargs) -> None:
        reload_secret_redactions()

    ctx.register_hook("on_session_start", _on_session_start)
    skill = Path(__file__).resolve().parent / "skills" / "secret-drop" / "SKILL.md"
    ctx.register_skill(
        "secret-drop",
        skill,
        description="Ask the user to enter a secret in the Desktop secure field, not in the chat.",
    )
