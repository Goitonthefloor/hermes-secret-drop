"""Land a user-supplied secret on the gateway host without showing it to the model.

The desktop half POSTs the value once to this plugin's API, which runs inside
the gateway process (local backend, remote gateway, or SSH tunnel). This module:

1. Opens a new owner-only file under the profile's ``secret-drops`` directory.
2. Writes the value and reads it back on the same file descriptor. The bytes
   read back are what gets stored.
3. Persists them with ``save_env_value_secure`` (profile ``.env``, mode ``0600``)
   and checks that ``load_env`` returns the same string.
4. Keeps the name out of ``terminal.env_passthrough``, so the value reaches a
   command only through the ``{{secret:NAME}}`` alias. A name that an earlier
   version added to that list is removed again, because an exported name lets a
   command read the value through ``$NAME`` and print it.
5. Overwrites and unlinks the file, including when a later step fails.

Nothing returned or logged contains the secret.
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_CHARS = 8192
_MAX_USERNAME_CHARS = 256
# A username stored next to a secret lives under this suffix. It is injectable through
# an alias like any stored name, but it is an account name, not a credential: making it
# a global output needle would rewrite every mention of the account.
_USERNAME_SUFFIX = "_USER"
_MIN_REDACTION_CHARS = 8
_LONG_REDACTION_CHARS = 24
_DROP_DIR = "secret-drops"
_NAMES_FILE = "secret-drop-names"
_STORE_LOCK = threading.RLock()


class SecretDropError(ValueError):
    """A refusal whose message is safe to show to the user."""


def registers_for_redaction(value: str) -> bool:
    """Whether *value* is safe to install as an exact-match output redaction.

    Vault redaction replaces every occurrence in tool output. A short value, or a
    string made only of letters, would rewrite ordinary text (``password``,
    ``administrator``). Digits or symbols mark a credential-shaped value; a very
    long letter string is specific enough on its own.
    """
    if not isinstance(value, str):
        return False
    if len(value) < _MIN_REDACTION_CHARS:
        return False
    if len(value) >= _LONG_REDACTION_CHARS:
        return True
    return any(not ch.isalpha() for ch in value)


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
            "beside the composer, and type the value in the secure field. The value stays "
            "out of the chat and the model context; the model uses {{secret:NAME}} in commands."
        )
    return (
        "To give Hermes a secret without putting it in the chat, open Hermes Desktop and "
        "press the key button beside the composer. The value is written into a file on this "
        "gateway host, saved as an environment variable, and the file is deleted. "
        "The value stays out of the chat and the model context; the model uses "
        "{{secret:NAME}} in commands."
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
    return _stored_line(result)


def accept_secret_for_profile(
    name: str, value: str, profile: str | None, username: str | None = None
) -> dict:
    """Store *value* in *profile* when the dashboard is serving more than one.

    ``None`` or the process's own profile keeps the request on this process home.
    A named profile uses the dashboard's config scope so the write cannot land in
    the launch profile's ``.env``.
    """
    try:
        from hermes_cli.web_server_profiles import _config_profile_scope
    except Exception:
        if (profile or "").strip():
            raise SecretDropError("could not select that profile") from None
        return accept_secret_file(name, value, username)
    with _config_profile_scope(profile):
        return accept_secret_file(name, value, username)


def accept_secret_file(name: str, value: str, username: str | None = None) -> dict:
    """Write ``value`` to a private file, store it as ``name``, then delete the file.

    An optional *username* is stored next to it as ``<NAME>_USER`` so a login can be
    used without the model inventing one. A username is not a secret and is not
    redacted from output, but it reaches a command through the same alias path.
    """
    name = (name or "").strip()
    username = _clean_username(username)
    _reject_value(value)
    try:
        from hermes_cli.config import validate_env_var_name_for_write

        validate_env_var_name_for_write(name)
    except ValueError as exc:
        raise SecretDropError(str(exc)) from None

    path: Path | None = None
    fd: int | None = None
    try:
        path, fd = _create_drop_file()
        _write_all(fd, value.encode("utf-8"))
        os.fsync(fd)
        stored = _read_fd(fd)
        if stored != value:
            raise SecretDropError("secret file was unreadable")
        with _STORE_LOCK:
            _persist_secret(name, stored)
            indexed = _try_remember_name(name)
            redacted = registers_for_redaction(stored)
            if redacted:
                _register_redaction(stored)
            revoke_name_passthrough(name)
            username_target = _store_username(name, username)
        return {
            "success": True,
            "stored_as": name,
            "injectable": secret_is_injectable(name),
            "redacted": redacted,
            "indexed": indexed,
            "username_stored_as": username_target,
            "message": "stored",
        }
    except SecretDropError:
        raise
    except Exception as exc:
        raise SecretDropError(_public_error(exc, value)) from None
    finally:
        if fd is not None:
            _wipe_fd(fd, path)


def reload_secret_redactions() -> None:
    """Register previously stored values so later tool output can redact them."""
    try:
        values = persisted_secret_values()
    except Exception:
        logger.debug("could not load persisted secret-drop redactions", exc_info=True)
        return
    for value in values:
        if registers_for_redaction(value):
            _register_redaction(value)


def is_account_name(name: str) -> bool:
    """True for ``<NAME>_USER``: injectable, but never used as an output needle."""
    return isinstance(name, str) and name.endswith(_USERNAME_SUFFIX)


def persisted_secret_values() -> list[str]:
    """Values previously stored here. Callers must not log the returned strings."""
    from hermes_cli.config import load_env

    env = load_env()
    values: list[str] = []
    for item in stored_secret_names():
        if is_account_name(item):
            continue
        value = env.get(item)
        if isinstance(value, str) and value:
            values.append(value)
    return values


def stored_secret_names() -> list[str]:
    """Names the user stored through this plugin. Values are never returned here."""
    return _read_names()


def secret_is_injectable(name: str) -> bool:
    """Whether *name* may be substituted into a command by the alias hook.

    Provider and platform credentials stay out of commands, mirroring the
    provider-credential blocklist. An unavailable blocklist fails closed.
    """
    return _can_passthrough(name)


def _stored_line(result: dict) -> str:
    line = f"Stored as {result['stored_as']}. Use {{{{secret:{result['stored_as']}}}}} in commands."
    if not result["injectable"]:
        line += " It cannot be used through the alias."
    if not result["redacted"]:
        line += " It is not scrubbed from tool output."
    if not result["indexed"]:
        line += " A later session may not scrub it."
    if result.get("username_stored_as"):
        target = result["username_stored_as"]
        line += f" The username is stored as {target}; use {{{{secret:{target}}}}} for it."
    return line


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
    """Log a secret-free detail for the server operator, return a generic refusal.

    Callers show the return value to the desktop or the terminal, so it never carries
    host exception text: that text can describe paths, backends, or the value itself.
    """
    detail = str(exc) or type(exc).__name__
    if secret:
        detail = detail.replace(secret, "[secret]")
    logger.warning("secret drop failed (%s): %s", type(exc).__name__, detail[:500])
    return "could not store secret"


def _clean_username(username: object) -> str | None:
    """Validate the optional username. Empty means "none"."""
    if username is None:
        return None
    if not isinstance(username, str):
        raise SecretDropError("username is not valid")
    value = username.strip()
    if not value:
        return None
    if len(value) > _MAX_USERNAME_CHARS:
        raise SecretDropError("username is too long")
    if not value.isascii() or any(ch in value for ch in "\r\n\x00"):
        raise SecretDropError("username is not valid")
    return value


def _store_username(name: str, username: str | None) -> str | None:
    """Store *username* as ``<NAME>_USER``. Never fails the secret it belongs to."""
    if not username:
        return None
    target = f"{name}_USER"
    try:
        from hermes_cli.config import validate_env_var_name_for_write

        validate_env_var_name_for_write(target)
        _persist_secret(target, username)
        _try_remember_name(target)
        return target
    except Exception:
        logger.warning("could not store the username for %s", name)
        return None


def _persist_secret(name: str, stored: str) -> None:
    from hermes_cli.config import load_env, save_env_value_secure

    save_env_value_secure(name, stored)
    if load_env().get(name) != stored:
        raise SecretDropError("could not store secret")


def _try_remember_name(name: str) -> bool:
    try:
        _remember_name(name)
    except SecretDropError:
        logger.warning("could not record secret-drop name %s", name)
        return False
    return True


def _open_flags(*flags: int) -> int:
    value = 0
    for flag in flags:
        value |= flag
    if hasattr(os, "O_CLOEXEC"):
        value |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        value |= os.O_NOFOLLOW
    return value


def _create_drop_file() -> tuple[Path, int]:
    from hermes_cli.config import ensure_hermes_home
    from hermes_constants import get_hermes_home

    ensure_hermes_home()
    directory = get_hermes_home() / _DROP_DIR
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise SecretDropError("secret drop directory must not be a symlink")
    dir_flags = _open_flags(os.O_RDONLY)
    if hasattr(os, "O_DIRECTORY"):
        dir_flags |= os.O_DIRECTORY
    try:
        dir_fd = os.open(directory, dir_flags)
    except OSError:
        raise SecretDropError("secret drop directory must not be a symlink") from None
    try:
        info = os.fstat(dir_fd)
        if not stat.S_ISDIR(info.st_mode):
            raise SecretDropError("secret drop directory must not be a symlink")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise SecretDropError("secret drop directory has the wrong owner")
        try:
            os.fchmod(dir_fd, 0o700)
        except OSError:
            pass
        filename = secrets.token_hex(16)
        fd = os.open(filename, _open_flags(os.O_CREAT, os.O_EXCL, os.O_RDWR), 0o600, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        pass
    return directory / filename, fd


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise SecretDropError("could not store secret")
        view = view[written:]


def _read_fd(fd: int) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
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
    return b"".join(chunks).decode("utf-8")


def _wipe_fd(fd: int, path: Path | None) -> None:
    try:
        size = os.fstat(fd).st_size
        os.lseek(fd, 0, os.SEEK_SET)
        if size:
            view = memoryview(os.urandom(size))
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    break
                view = view[written:]
            os.fsync(fd)
        os.ftruncate(fd, 0)
        os.fsync(fd)
    except Exception:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    if path is None:
        return
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
        fd = os.open(tmp, _open_flags(os.O_CREAT, os.O_EXCL, os.O_WRONLY), 0o600)
        try:
            try:
                _write_all(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
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


def revoke_name_passthrough(name: str) -> list[str]:
    """Stop ``terminal.env_passthrough`` from forwarding *name*. Returns what was removed.

    Never raises: a config that cannot be rewritten must not fail the store operation,
    and the guard covers the leftover with a per-call scrub.
    """
    try:
        return _revoke_passthrough({name})
    except Exception:
        logger.warning("could not revoke env passthrough for %s", name)
        return []


def revoke_stored_passthrough() -> list[str]:
    """Migration: drop every stored name from ``terminal.env_passthrough``.

    Versions before 1.5.1 added each stored name to that list so commands could expand
    ``$NAME``. That handed the value to any command that printed its own environment,
    which defeats the isolation the alias provides. Called once per session.
    """
    names = set(stored_secret_names())
    if not names:
        return []
    try:
        return _revoke_passthrough(names)
    except Exception:
        logger.warning("could not clean stored names out of env passthrough")
        return []


def _revoke_passthrough(names: set[str]) -> list[str]:
    from hermes_cli import config as config_mod

    lock = getattr(config_mod, "_CONFIG_LOCK", None)
    if lock is None:
        removed = _revoke_passthrough_names(config_mod, names)
    else:
        with lock:
            removed = _revoke_passthrough_names(config_mod, names)
    if not removed:
        return []
    try:
        from tools import env_passthrough
    except Exception:
        return removed
    _invalidate_passthrough_cache(env_passthrough)
    unregister = getattr(env_passthrough, "unregister_env_passthrough", None)
    if callable(unregister):
        for name in removed:
            try:
                unregister(name)
            except Exception:
                logger.warning("could not unregister env passthrough for %s", name)
    # No unregister API exists in the core registry: the skill allowlist is a plain
    # process-wide set, so a name registered by an earlier version stays forwarded
    # until the process restarts unless it is dropped here.
    allowed = getattr(env_passthrough, "_allowed_env_vars", None)
    if isinstance(allowed, set):
        for name in removed:
            allowed.discard(name)
    return removed


def _revoke_passthrough_names(config_mod, names: set[str]) -> list[str]:
    raw = config_mod.require_readable_config_before_write()
    terminal = raw.get("terminal")
    if not isinstance(terminal, dict):
        return []
    current = terminal.get("env_passthrough")
    if not isinstance(current, list):
        return []
    removed = [
        item for item in current if isinstance(item, str) and item in names
    ]
    if not removed:
        return []
    terminal["env_passthrough"] = [
        item
        for item in current
        if not (isinstance(item, str) and item in names)
    ]
    config_mod.save_config(raw, preserve_keys={("terminal", "env_passthrough")})
    return removed


def _invalidate_passthrough_cache(env_passthrough) -> None:
    invalidate = getattr(env_passthrough, "invalidate_config_passthrough", None)
    if callable(invalidate):
        invalidate()
        return
    cache = getattr(env_passthrough, "_config_passthrough", None)
    if isinstance(cache, dict):
        cache.clear()


def _stream_is_tty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False
