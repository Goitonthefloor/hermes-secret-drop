"""Keep stored secret values inside the gateway process.

The model never holds a secret value. It writes an alias, ``{{secret:NAME}}``,
into a ``terminal`` command or ``execute_code`` body; the ``pre_tool_call``
hook in this module replaces the alias with the stored value in the arguments
that are about to be executed (``{"action": "modify"}``). Replaced arguments
are used for the execution only and are not written back into the transcript,
so the value stays out of the model context.

Three guards live here, all registered from ``__init__.py``:

* :func:`pre_tool_call` — alias substitution plus a fail-closed read guard on
  the secret store (``$HERMES_HOME/.env``, ``secret-drop-names``, and
  ``secret-drops/``) via ``read_file``, ``search_files``, ``terminal``, and
  ``execute_code``.
* :func:`transform_terminal_output` and :func:`transform_tool_result` — scrub
  stored values and their common encodings out of tool output before it
  reaches the model.

No function in this module returns or logs a secret value.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote, quote_plus

try:  # package import (the normal Hermes path)
    from . import secret_drop as _drop
except ImportError:  # loaded as a loose module rather than a package
    import secret_drop as _drop

logger = logging.getLogger(__name__)

REDACTED = "«redacted-vault-secret»"

_ALIAS_RE = re.compile(r"\{\{\s*secret:([^{}\s]*)\s*\}\}")
_ALIAS_RESIDUE_RE = re.compile(r"\{\{\s*secret:")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARG_FIELD = {"terminal": "command", "execute_code": "code"}
_READER_RE = re.compile(
    r"(?:^|[\s;|&()`<>])(?:cat|tac|head|tail|less|more|most|grep|egrep|fgrep|rg|"
    r"strings|awk|sed|base64|base32|hexdump|xxd|od|nl|cut|sort|uniq|tr|dd|cp|"
    r"install|python[0-9.]*|perl|ruby|node|php)\b"
)
_HERMES_STORE_RE = re.compile(
    r"\.hermes[^\s'\"`]*?/(?:secret-drop-names|secret-drops|\.env)(?![\w-])"
)
_SECRET_DROPS_RE = re.compile(r"(?<![\w-])secret-drops(?![\w-])")
_SECRET_NAMES_RE = re.compile(r"(?<![\w-])secret-drop-names(?![\w-])")
_DOT_ENV_RE = re.compile(r"(?<![\w.-])\.env(?![\w.-])")
_INTERPRETER_READ_RE = re.compile(r"\bopen\s*\(|\bread\s*\(|\bread_text\s*\(|\bio\.open\b")

_BLOCK_READ = (
    "Blocked: {what} is part of the secret store and cannot be read, listed, or "
    "inspected from a tool call. To use a stored secret, reference it as "
    "{{{{secret:NAME}}}} inside the command or code; the gateway substitutes the value "
    "when it runs the call."
)
_BLOCK_ALIAS_UNKNOWN = (
    "The alias {{{{secret:{name}}}}} does not match a secret stored on this gateway. "
    "Ask the user to store it with the key button in Hermes Desktop or with /secret in a "
    "local terminal, then use the alias only. Never ask for the value in the chat."
)
_BLOCK_ALIAS_EMPTY = (
    "The secret behind {{{{secret:{name}}}}} is empty, so nothing can be substituted. "
    "Ask the user to store it again in Hermes Desktop or with /secret in a local terminal."
)
_BLOCK_ALIAS_NAME = (
    "{{{{secret:{name}}}}} is not a valid secret alias. Use {{{{secret:NAME}}}} with an "
    "environment variable name such as {{{{secret:DEPLOY_PASSWORD}}}}."
)
_BLOCK_ALIAS_CREDENTIAL = (
    "{{{{secret:{name}}}}} names a provider credential, which is stored but never injected "
    "into commands. Use the provider through Hermes instead of the raw value."
)
_BLOCK_GUARD_FAILED = (
    "Blocked: the secret isolation guard could not evaluate this call, so it was refused. "
    "Retry the call; to use a stored secret, reference it as {{{{secret:NAME}}}}."
)


def pre_tool_call(tool_name: str = "", args: dict | None = None, **_kwargs) -> dict | None:
    """Substitute aliases and guard the secret store before a tool runs.

    Returns ``None`` to leave the call untouched, ``{"action": "modify", "args": ...}``
    with the value only in the in-memory execution arguments, or
    ``{"action": "block", "message": ...}``. The block message never contains a value.
    """
    try:
        return _pre_tool_call(tool_name, args if isinstance(args, dict) else {})
    except Exception:
        logger.warning("secret-drop guard failed; blocking the tool call")
        return {"action": "block", "message": _BLOCK_GUARD_FAILED}


def transform_terminal_output(output: str = "", **_kwargs) -> str | None:
    """Scrub stored secret values from terminal output before it reaches the model."""
    try:
        if not isinstance(output, str) or not output:
            return None
        cleaned = scrub_text(output)
        return cleaned if cleaned != output else None
    except Exception:
        logger.warning("secret-drop terminal output scrub failed; withholding output")
        return "[secret-drop] output withheld: secret redaction failed."


def transform_tool_result(result: object = None, **_kwargs) -> str | None:
    """Scrub stored secret values from any tool result string before it reaches the model."""
    try:
        if not isinstance(result, str) or not result:
            return None
        cleaned = scrub_text(result)
        return cleaned if cleaned != result else None
    except Exception:
        logger.warning("secret-drop tool result scrub failed; withholding result")
        return "[secret-drop] output withheld: secret redaction failed."


def _pre_tool_call(tool_name: str, args: dict) -> dict | None:
    blocked = guard_store_access(tool_name, args)
    if blocked:
        return {"action": "block", "message": blocked}
    field = _ARG_FIELD.get(tool_name)
    if not field:
        return None
    text = args.get(field)
    if not isinstance(text, str) or "{{" not in text or "secret:" not in text:
        return None
    resolved, error = substitute_aliases(text)
    if error:
        return {"action": "block", "message": error}
    if resolved is None or resolved == text:
        return None
    return {"action": "modify", "args": {field: resolved}}


def substitute_aliases(text: str) -> tuple[str | None, str | None]:
    """Replace every ``{{secret:NAME}}`` in *text*.

    Returns ``(resolved_text, None)`` or ``(None, block_message)``. The message never
    contains a value; the resolved text does, and must only be used for execution.
    """
    error: list[str] = []

    def _replace(match: re.Match) -> str:
        if error:
            return match.group(0)
        name = match.group(1).strip()
        if not _ENV_NAME_RE.match(name):
            error.append(_BLOCK_ALIAS_NAME.format(name=name))
            return match.group(0)
        status, value = resolve_alias(name)
        if status == "unknown":
            error.append(_BLOCK_ALIAS_UNKNOWN.format(name=name))
            return match.group(0)
        if status == "credential":
            error.append(_BLOCK_ALIAS_CREDENTIAL.format(name=name))
            return match.group(0)
        if status == "empty":
            error.append(_BLOCK_ALIAS_EMPTY.format(name=name))
            return match.group(0)
        return value

    resolved = _ALIAS_RE.sub(_replace, text)
    if error:
        return None, error[0]
    if _ALIAS_RESIDUE_RE.search(resolved):
        return None, _BLOCK_ALIAS_NAME.format(name="NAME")
    return resolved, None


def resolve_alias(name: str) -> tuple[str, str]:
    """``(status, value)`` for *name*: ``ok`` / ``unknown`` / ``empty`` / ``credential``.

    Only names the user stored through this plugin resolve. Provider credentials are
    stored but not injectable, matching the existing passthrough policy.
    """
    if name not in _drop.stored_secret_names():
        return "unknown", ""
    if not _drop.secret_is_injectable(name):
        return "credential", ""
    from hermes_cli.config import load_env

    value = load_env().get(name)
    if not isinstance(value, str) or value == "":
        return "empty", ""
    return "ok", value


def guard_store_access(tool_name: str, args: dict) -> str | None:
    """Block direct reads of the secret store. Returns a message or ``None``.

    ``read_file`` and ``search_files`` are checked on the resolved path; a search over a
    directory that contains the store is blocked when its pattern or glob names the
    store. ``terminal`` and ``execute_code`` are checked on the text, with fail-closed
    handling for unresolved spellings such as ``$HERMES_HOME`` when the variable is not
    set in this process.
    """
    if tool_name == "read_file":
        return _guard_read_file(args)
    if tool_name == "search_files":
        return _guard_search_files(args)
    if tool_name in ("terminal", "execute_code"):
        return _guard_command_text(args.get(_ARG_FIELD[tool_name]))
    return None


def _guard_read_file(args: dict) -> str | None:
    raw = args.get("path")
    target = _store_target(raw)
    if target is None:
        return None
    return _BLOCK_READ.format(what=target)


def _guard_search_files(args: dict) -> str | None:
    raw = args.get("path")
    target = _store_target(raw)
    if target is not None:
        return _BLOCK_READ.format(what=target)
    resolved = _resolve_path(raw)
    if resolved is None:
        return None
    hint = " ".join(
        str(args.get(key) or "") for key in ("pattern", "file_glob")
    ).lower()
    for guarded in guarded_paths():
        if guarded == resolved or guarded in resolved.parents:
            continue
        if resolved == guarded.parent or resolved in guarded.parents:
            if guarded.name in hint or ".env" in hint or "secret-drop" in hint:
                return _BLOCK_READ.format(what=guarded.name)
    return None


def _guard_command_text(text: object) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    target = _store_text_target(text)
    if target is None:
        return None
    if not _READER_RE.search(text) and not _INTERPRETER_READ_RE.search(text) and "<" not in text:
        # No reader and no opening access: the command cannot dump the store. Blocking
        # here would refuse harmless bookkeeping, so only fail closed for the readers.
        return None
    return _BLOCK_READ.format(what=target)


def guarded_paths() -> list[Path]:
    """The three store locations under the active Hermes home."""
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    return [home / ".env", home / "secret-drop-names", home / "secret-drops"]


def _store_target(raw: object) -> str | None:
    """Name of the guarded path *raw* resolves to, or ``None``."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    ambiguous = _ambiguous_text_reference(raw)
    if ambiguous is not None:
        return ambiguous
    resolved = _resolve_path(raw)
    if resolved is None:
        return None
    for guarded in guarded_paths():
        if resolved == guarded:
            return guarded.name
        if guarded.name == "secret-drops" and guarded in resolved.parents:
            return "secret-drops/"
    return None


def _store_text_target(text: str) -> str | None:
    lowered = text.lower()
    if _HERMES_STORE_RE.search(lowered):
        return "a file under $HERMES_HOME"
    if _SECRET_DROPS_RE.search(lowered):
        return "secret-drops/"
    if _SECRET_NAMES_RE.search(lowered):
        return "secret-drop-names"
    if _DOT_ENV_RE.search(text) and ("hermes" in lowered or "hermes_home" in lowered):
        return "a .env file under $HERMES_HOME"
    return None


def _ambiguous_text_reference(raw: str) -> str | None:
    """Fail closed when a path string names the store but does not resolve here."""
    lowered = raw.lower()
    if "hermes_home" in lowered or "$hermes" in lowered:
        if ".env" in lowered or "secret-drop" in lowered:
            return "a file under $HERMES_HOME"
    if "secret-drop" in lowered:
        return "secret-drops/"
    if ".env" in lowered and ("hermes" in lowered or "~/" in lowered):
        return "a .env file under $HERMES_HOME"
    return None


def _resolve_path(raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().strip("'\"")
    expanded = os.path.expandvars(os.path.expanduser(text))
    if "$" in expanded:
        return None
    try:
        return Path(expanded).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def load_secret_values() -> list[str]:
    """Values eligible for scrubbing, loaded once per call. Never log these."""
    try:
        values = _drop.persisted_secret_values()
    except Exception:
        logger.warning("secret-drop could not load stored values for scrubbing")
        return []
    return [value for value in values if _drop.registers_for_redaction(value)]


def scrub_text(text: str, values: list[str] | None = None) -> str:
    """Replace stored values and their common encodings with ``REDACTED``."""
    if not isinstance(text, str) or not text:
        return text
    if values is None:
        values = load_secret_values()
    variants = encoded_variants(values)
    for variant in variants:
        if variant in text:
            text = text.replace(variant, REDACTED)
    return text


def encoded_variants(values: list[str]) -> list[str]:
    """Every needle to remove for *values*, longest first, duplicates dropped.

    A needle never shadows a superstring, and no needle is emitted for a value that
    ``registers_for_redaction`` rejects (short values and plain words would rewrite
    ordinary text).
    registers_for_redaction is applied per value: short values and plain words are never
    used as needles.
    """
    needles: set[str] = set()
    for value in values:
        if not _drop.registers_for_redaction(value):
            continue
        raw = value.encode("utf-8")
        forms = {
            value,
            value[::-1],
            raw.hex(),
            raw.hex().upper(),
            quote(value, safe=""),
            quote_plus(value, safe=""),
            base64.b64encode(raw).decode("ascii"),
            base64.urlsafe_b64encode(raw).decode("ascii"),
        }
        forms |= {form.rstrip("=") for form in list(forms) if form}
        for separator in (" ", ".", "#"):
            forms.add(separator.join(value))
        needles.update(form for form in forms if form)
    return sorted(needles, key=len, reverse=True)
