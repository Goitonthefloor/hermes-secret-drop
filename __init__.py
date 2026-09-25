"""Secret drop plugin: store a secret on the gateway host, never in the chat."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

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
    register_section = getattr(ctx, "register_system_prompt_section", None)
    if callable(register_section):
        try:
            register_section(
                "secret-drop",
                (
                    "When a task needs a password, token, or other secret, do not ask the user "
                    "to paste it into the chat, a tool argument, or a file. Ask them to use the "
                    "key button beside the Hermes Desktop composer (Give Hermes a secret) or "
                    "`/secret` in a local terminal. Use only the environment variable name they "
                    "give you. Do not print, log, or encode that variable."
                ),
            )
        except Exception:
            logger.warning("could not register secret-drop session prompt", exc_info=True)
    skill = Path(__file__).resolve().parent / "skills" / "secret-drop" / "SKILL.md"
    ctx.register_skill(
        "secret-drop",
        skill,
        description="Ask the user to enter a secret in the Desktop secure field, not in the chat.",
    )
