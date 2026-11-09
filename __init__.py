"""Secret drop plugin: store a secret on the gateway host, never in the chat."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from .secret_drop import (
        reload_secret_redactions,
        revoke_stored_passthrough,
        run_secret_command,
    )
    from .secret_guard import pre_tool_call, transform_terminal_output, transform_tool_result
except ImportError:  # loaded as a loose module rather than a package
    from secret_drop import (
        reload_secret_redactions,
        revoke_stored_passthrough,
        run_secret_command,
    )
    from secret_guard import pre_tool_call, transform_terminal_output, transform_tool_result


def register(ctx) -> None:
    ctx.register_command(
        "secret",
        run_secret_command,
        description="Store a secret as an environment variable without showing it to the model",
        args_hint="[NAME]",
    )

    def _on_session_start(**_kwargs) -> None:
        reload_secret_redactions()
        revoke_stored_passthrough()

    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("transform_terminal_output", transform_terminal_output)
    ctx.register_hook("transform_tool_result", transform_tool_result)
    register_section = getattr(ctx, "register_system_prompt_section", None)
    if callable(register_section):
        try:
            register_section(
                "secret-drop",
                (
                    "Secrets live on the gateway host, never in the chat or your context. "
                    "The only way to use one is the alias {{secret:NAME}} inside a terminal "
                    "command or execute_code body: the gateway replaces the placeholder with "
                    "the stored value when it runs the call, so the value never appears in "
                    "the prompt, a tool argument you write, or a tool result. Do not print, "
                    "copy, log, decode, or otherwise reveal the value, and do not ask the "
                    "user to paste it into the chat or a file. Direct reads of the secret "
                    "store (.env, secret-drop-names, secret-drops/) are blocked; if an alias "
                    "is missing, ask the user to store the secret with the key button in "
                    "Hermes Desktop or with /secret in a local terminal. The stored name is "
                    "not exported into the tool environment, so $NAME is not a path to the "
                    "value: use the alias, and do not dump the environment to look for it."
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
