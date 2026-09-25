"""Land a user-supplied secret on the gateway host without showing it to the model.

The desktop half POSTs the value once to this plugin's API, which runs inside
the gateway process (local backend, remote gateway, or SSH tunnel). This module:

1. Opens a new owner-only file under the profile's ``secret-drops`` directory.
2. Writes the value and reads it back. The file is what gets stored.
3. Persists it with ``save_env_value_secure`` (profile ``.env``, mode ``0600``).
4. Allows the name through ``terminal.env_passthrough`` when it is not a provider
   credential, so later commands can use ``$NAME``.
5. Overwrites and unlinks the file, including when a later step fails.

Nothing returned or logged contains the secret.
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_CHARS = 8192
_DROP_DIR = "secret-drops"
_NAMES_FILE = "secret-drop-names"


class SecretDropError(ValueError):
    """A refusal whose message is safe to show to the user."""


def command_name_token(raw: str) -> tuple[str, bool]:
    """Return ``(name, inline_value_rejected)``.

    A slash command may carry an optional variable name. A second token, or
    ``NAME=value``, is treated as an inline secret and discarded. The discarded
    text is never returned.
    """
    parts = (raw or "").strip().split()
    if parts and parts[0].startswith("/"):
        parts = parts[1:]
    if not parts:
        return "", False
    if len(parts) > 1 or "=" in parts[0]:
        return "", True
    return parts[0], False


def messaging_secret_reply(raw: str) -> str:
    """Reply for a chat-platform ``/secret``. Never echoes the argument."""
    name, rejected = command_name_token(raw)
    if rejected:
        return (
            "Nothing was stored. Do not send a secret in this chat — it would stay in the "
            "history and be shown to the model. Delete the message if it contains one. "
            "Use Hermes Desktop (the key button beside the composer) or a local terminal."
        )
    if name:
        return (
            "Nothing was stored from this chat. Open Hermes Desktop, use the key button "
            "beside the composer, and type the value in the secure field. The model never sees it."
        )
    return (
        "To give Hermes a secret without putting it in the chat, open Hermes Desktop and "
        "press the key button beside the composer. The value is written into a file on this "
        "gateway host, saved as an environment variable, and the file is deleted. "
        "The model never sees the value."
    )


def run_secret_command(raw: str) -> str:
    """``/secret`` for the CLI and the messaging gateway. The text never contains the secret."""
    name, rejected = command_name_token(raw)
    if rejected:
        return (
            "Nothing was stored. The command only accepts a variable name.\n"
            "Type the secret at the hidden prompt, or use the Desktop secure field."
        )
    if not _stream_is_tty(sys.stdin) or not _stream_is_tty(sys.stdout):
        return messaging_secret_reply(raw)
    from hermes_cli.cli_output import line_input
    from hermes_cli.secret_prompt import masked_secret_prompt

    if not name:
        name = line_input("Variable name (example: DEPLOY_PASSWORD): ").strip()
    if not name or any(ch.isspace() for ch in name) or "=" in name:
        return "Use a variable name like DEPLOY_PASSWORD. Nothing was stored."
    value = masked_secret_prompt("Secret (hidden, empty cancels): ")
    if not value:
        return "Cancelled. Nothing was stored."
    try:
        result = accept_secret_file(name, value)
    except SecretDropError as exc:
        return f"{exc}\nNothing was stored."
    except Exception:
        logger.warning("secret drop failed for %s", name)
        return "Could not store the secret."
    line = f"Stored as {result['stored_as']}. The model was not shown the value."
    if not result["passthrough"]:
        line += " It is not forwarded into sandboxed commands."
    return line


def accept_secret_file(name: str, value: str) -> dict:
    """Write ``value`` to a private file, store it as ``name``, then delete the file."""
    name = (name or "").strip()
    _reject_value(value)
    try:
        from hermes_cli.config import validate_env_var_name_for_write

        validate_env_var_name_for_write(name)
    except ValueError as exc:
        raise SecretDropError(str(exc)) from None

    path: Path | None = None
    try:
        path = _create_drop_file()
        _write_secret(path, value)
        stored = _read_secret(path)
        if stored != value:
            raise SecretDropError("secret file was unreadable")
        from hermes_cli.config import save_env_value_secure

        save_env_value_secure(name, stored)
        try:
            _remember_name(name)
        except SecretDropError:
            logger.warning("could not record secret-drop name %s", name)
        _register_redaction(stored)
        try:
            passthrough = _allow_passthrough(name)
        except Exception:
            logger.warning("could not enable env passthrough for %s", name)
            passthrough = False
        return {
            "success": True,
            "stored_as": name,
            "passthrough": passthrough,
            "message": "stored",
        }
    except SecretDropError:
        raise
    except Exception as exc:
        logger.warning("secret drop failed for %s", name)
        raise SecretDropError(_public_error(exc, value)) from None
    finally:
        if path is not None:
            _wipe(path)


def reload_secret_redactions() -> None:
    """Register previously stored values so later tool output can redact them."""
    try:
        values = persisted_secret_values()
    except Exception:
        logger.debug("could not load persisted secret-drop redactions", exc_info=True)
        return
    for value in values:
        _register_redaction(value)


def persisted_secret_values() -> list[str]:
    """Values previously stored here. Callers must not log the returned strings."""
    from hermes_cli.config import load_env

    env = load_env()
    values: list[str] = []
    for item in _read_names():
        value = env.get(item)
        if isinstance(value, str) and value:
            values.append(value)
    return values


def _reject_value(value: object) -> None:
    if not isinstance(value, str) or value == "":
        raise SecretDropError("secret is empty")
    if len(value) > _MAX_CHARS:
        raise SecretDropError("secret is too long")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise SecretDropError("secret cannot contain line breaks")
    if not value.isascii():
        raise SecretDropError("secret must be ASCII")


def _public_error(exc: BaseException, secret: str) -> str:
    text = str(exc) or "could not store secret"
    if secret and secret in text:
        return "could not store secret"
    return text


def _create_drop_file() -> Path:
    from hermes_cli.config import ensure_hermes_home
    from hermes_constants import get_hermes_home

    ensure_hermes_home()
    directory = get_hermes_home() / _DROP_DIR
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise SecretDropError("secret drop directory must not be a symlink")
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    path = directory / secrets.token_hex(16)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
    except OSError:
        pass
    finally:
        os.close(fd)
    return path


def _open_nofollow(path: Path, flags: int) -> int:
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags)


def _write_secret(path: Path, value: str) -> None:
    fd = _open_nofollow(path, os.O_WRONLY)
    try:
        os.write(fd, value.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_secret(path: Path) -> str:
    fd = _open_nofollow(path, os.O_RDONLY)
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(fd, 4096)
            if not block:
                break
            total += len(block)
            if total > _MAX_CHARS:
                raise SecretDropError("secret file was unreadable")
            chunks.append(block)
    finally:
        os.close(fd)
    return b"".join(chunks).decode("utf-8")


def _wipe(path: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    try:
        fd = _open_nofollow(path, os.O_WRONLY)
        try:
            if size:
                os.write(fd, os.urandom(size))
                os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass
    try:
        os.unlink(path)
    except OSError:
        logger.warning("could not delete secret drop file %s", path.name)


def _names_path() -> Path:
    from hermes_constants import get_hermes_home

    return get_hermes_home() / _NAMES_FILE


def _read_names() -> list[str]:
    path = _names_path()
    if path.is_symlink() or not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    names: list[str] = []
    for line in text.splitlines():
        item = line.strip()
        if item and item not in names:
            names.append(item)
    return names


def _remember_name(name: str) -> None:
    try:
        path = _names_path()
        if path.is_symlink():
            raise SecretDropError("secret name index must not be a symlink")
        names = _read_names()
        if name in names:
            return
        names.append(name)
        data = ("\n".join(names) + "\n").encode("utf-8")
        tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(tmp, flags, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise SecretDropError("could not record secret name") from None
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except SecretDropError:
        raise
    except OSError:
        raise SecretDropError("could not record secret name") from None


def _register_redaction(value: str) -> None:
    try:
        from agent.redact import register_vault_redaction_value

        register_vault_redaction_value(value)
    except Exception:
        logger.warning("could not register secret for output redaction")


def _can_passthrough(name: str) -> bool:
    try:
        from tools.env_passthrough import _is_hermes_provider_credential
    except Exception:
        logger.warning("env passthrough blocklist unavailable; refusing passthrough for %s", name)
        return False
    return not _is_hermes_provider_credential(name)


def _allow_passthrough(name: str) -> bool:
    from tools import env_passthrough

    if not _can_passthrough(name):
        return False
    from hermes_cli.config import load_config, save_config

    cfg = load_config()
    terminal = cfg.get("terminal")
    if not isinstance(terminal, dict):
        terminal = {}
        cfg["terminal"] = terminal
    current = terminal.get("env_passthrough")
    names = [item for item in current if isinstance(item, str)] if isinstance(current, list) else []
    if name not in names:
        names.append(name)
        terminal["env_passthrough"] = names
        save_config(cfg, preserve_keys={("terminal", "env_passthrough")})
    invalidate = getattr(env_passthrough, "invalidate_config_passthrough", None)
    if callable(invalidate):
        invalidate()
    else:
        cache = getattr(env_passthrough, "_config_passthrough", None)
        if isinstance(cache, dict):
            cache.clear()
    env_passthrough.register_env_passthrough([name])
    return env_passthrough.is_env_passthrough(name)


def _stream_is_tty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False
