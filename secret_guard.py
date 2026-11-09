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
# Tools that write a file. Their target path is checked against the store, so the name
# index cannot be emptied with write_file or a patch instead of a shell command.
_WRITE_TOOLS = {
    "write_file", "patch", "edit", "str_replace", "apply_patch", "create_file",
    "append_file", "multiedit",
}
_WRITE_PATH_FIELDS = ("path", "file_path", "filename", "target")
_READER_HINT_RE = re.compile(
    r"\b(?:cat|tac|head|tail|less|more|grep|egrep|rg|strings|awk|sed|base64|xxd|od|"
    r"nl|cut|sort|uniq|tr|jq|python[0-9.]*|perl|ruby|node|php|source|sh|bash)\b|>>?"
)

_HERMES_STORE_RE = re.compile(
    r"\.hermes[^\s'\"`]{0,512}?/(?:secret-drop-names|secret-drops|\.env)(?![\w-])"
)
# Any spelling that looks like the plugin's store, including globs and separators:
# `secret-drop-names`, `secret_drop_names`, `secret*drop*`, `secret?drop*`.
_STORE_FRAGMENT_RE = re.compile(r"secret[\s*?_-]*drop")
# A command that both mentions the Hermes home and mutates files could relocate or
# erase the store, which would leave the scrubber without needles.
_HERMES_HOME_TEXT_RE = re.compile(r"\.hermes|hermes_home", re.IGNORECASE)
_MUTATING_RE = re.compile(
    r"\b(?:rm|rmdir|mv|cp|dd|truncate|shred|unlink|tee|install|ln|chmod|chown|"
    r"find|rsync|tar|zip)\b|>>?(?!=)"
)
_SECRET_DROPS_RE = re.compile(r"(?<![\w-])secret-drops(?![\w-])")
_SECRET_NAMES_RE = re.compile(r"(?<![\w-])secret-drop-names(?![\w-])")
_DOT_ENV_RE = re.compile(r"(?<![\w.-])\.env(?![\w.-])")
# Names whose values are treated as credentials when they appear in the profile .env,
# so a key Hermes wrote itself becomes a scrubber needle without indexing it first.
# Paths and model names are deliberately not on this list: rewriting every diagnostic
# path in tool output would make the plugin unusable without protecting anything.
_CREDENTIAL_NAME_RE = re.compile(
    r"(?:API|KEY|TOKEN|SECRET|PASSW|PASSWORD|CREDENTIAL|AUTH|COOKIE|SESSION|PRIVATE|DSN|URL)",
    re.IGNORECASE,
)

_BLOCK_READ = (
    "Blocked: {what} is part of the secret store and cannot be read, listed, or "
    "inspected from a tool call. To use a stored secret, reference it as "
    "{{{{secret:NAME}}}} inside the command or code; the gateway substitutes the value "
    "when it runs the call."
)
_BLOCK_WRITE = (
    "Blocked: {what} belongs to the secret store, so it cannot be overwritten or "
    "patched from a tool call. Store and rotate secrets through secret-drop itself; "
    "use {{{{secret:NAME}}}} to read one at execution time."
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

# Values substituted into a call, kept per tool_call_id so the scrubber can remove them
# from that call's output even when they are too short or too word-like to be a global
# needle. Bounded and value-only; entries are dropped when the call finishes.
_INJECTED: dict[str, list[str]] = {}
_INJECTED_MAX_CALLS = 128


def _remember_injection(tool_call_id: str, values: list[str]) -> None:
    if not values:
        return
    key = tool_call_id or ""
    _INJECTED[key] = list(values)
    while len(_INJECTED) > _INJECTED_MAX_CALLS:
        _INJECTED.pop(next(iter(_INJECTED)))


def _injected_values(**kwargs) -> list[str]:
    """Values injected for this tool call, if the hook was told which call it is.

    A dispatch path that carries no ``tool_call_id`` shares one fallback bucket, so a
    substitution is still scrubbed from the next output instead of being forgotten.
    """
    key = kwargs.get("tool_call_id")
    values: list[str] = []
    if isinstance(key, str) and key:
        values.extend(_INJECTED.get(key, ()))
    values.extend(_INJECTED.get("", ()))
    return values


def pre_tool_call(tool_name: str = "", args: dict | None = None, **kwargs) -> dict | None:
    """Substitute aliases and guard the secret store before a tool runs.

    Returns ``None`` to leave the call untouched, ``{"action": "modify", "args": ...}``
    with the value only in the in-memory execution arguments, or
    ``{"action": "block", "message": ...}``. The block message never contains a value.
    """
    try:
        return _pre_tool_call(tool_name, args if isinstance(args, dict) else {}, **kwargs)
    except Exception:
        logger.warning("secret-drop guard failed; blocking the tool call")
        return {"action": "block", "message": _BLOCK_GUARD_FAILED}


def transform_terminal_output(output: str = "", **kwargs) -> str | None:
    """Scrub stored secret values from terminal output before it reaches the model."""
    try:
        if not isinstance(output, str) or not output:
            return None
        cleaned = scrub_text(output, injected=_injected_values(**kwargs))
        return cleaned if cleaned != output else None
    except Exception:
        logger.warning("secret-drop terminal output scrub failed; withholding output")
        return "[secret-drop] output withheld: secret redaction failed."


def transform_tool_result(result: object = None, **kwargs) -> str | None:
    """Scrub stored secret values from any tool result string before it reaches the model."""
    try:
        if not isinstance(result, str) or not result:
            return None
        cleaned = scrub_text(result, injected=_injected_values(**kwargs))
        return cleaned if cleaned != result else None
    except Exception:
        logger.warning("secret-drop tool result scrub failed; withholding result")
        return "[secret-drop] output withheld: secret redaction failed."


def _pre_tool_call(tool_name: str, args: dict, **kwargs) -> dict | None:
    blocked = guard_store_access(tool_name, args)
    if blocked:
        return {"action": "block", "message": blocked}
    field = _ARG_FIELD.get(tool_name)
    if not field:
        return None
    text = args.get(field)
    if not isinstance(text, str) or "{{" not in text or "secret:" not in text:
        return None
    injected: list[str] = []
    resolved, error = substitute_aliases(text, collected=injected)
    if error:
        return {"action": "block", "message": error}
    if resolved is None or resolved == text:
        return None
    _remember_injection(str(kwargs.get("tool_call_id") or ""), injected)
    return {"action": "modify", "args": {field: resolved}}


def substitute_aliases(text: str, collected: list[str] | None = None) -> tuple[str | None, str | None]:
    """Replace every ``{{secret:NAME}}`` in *text*.

    Returns ``(resolved_text, None)`` or ``(None, block_message)``. Every substituted
    value is appended to *collected* so the caller can scrub it from the output. The
    message never contains a value; the resolved text does, and must only be used for
    execution.
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
        if collected is not None:
            collected.append(value)
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
    """Block reads and writes of the secret store. Returns a message or ``None``.

    ``read_file``, ``search_files`` and every tool that writes a file are checked on the
    resolved path, so the store cannot be read or emptied through ``write_file``,
    ``patch`` or an equivalent. ``search_files`` over a directory that contains the
    store is blocked as well. ``terminal`` and ``execute_code`` are checked on the text,
    with fail-closed handling for unresolved spellings such as ``$HERMES_HOME``.
    """
    if tool_name == "read_file":
        return _guard_read_file(args)
    if tool_name == "search_files":
        return _guard_search_files(args)
    if tool_name in _WRITE_TOOLS:
        return _guard_write(args)
    if tool_name in ("terminal", "execute_code"):
        return _guard_command_text(args.get(_ARG_FIELD[tool_name]))
    return None


def _guard_write(args: dict) -> str | None:
    """Refuse a write or patch whose target is the store."""
    for key in _WRITE_PATH_FIELDS:
        target = _store_target(args.get(key))
        if target is not None:
            return _BLOCK_WRITE.format(what=target)
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
    # A content search over any directory that contains or equals the store can return
    # its lines, whatever the pattern says. Blocking the ancestor is the only reliable
    # answer; narrowing a recursive search is not.
    for guarded in guarded_paths():
        if resolved == guarded or resolved in guarded.parents or guarded in resolved.parents:
            return _BLOCK_READ.format(what=guarded.name)
    return None


def _guard_command_text(text: object) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    target = _store_text_target(text)
    if target is not None:
        # Any command that names the store is refused. Allowing non-reader mentions
        # would let `mv`/`rm`/`cp` relocate or erase the store, after which nothing is
        # left to scrub, and a quoted reader slips past a reader-word test anyway.
        return _BLOCK_READ.format(what=target)
    if _STORE_FRAGMENT_RE.search(text.lower()) and (
        _MUTATING_RE.search(text) or _READER_HINT_RE.search(text)
    ):
        # A glob or odd separator (`secret*drop*`, `secret_drop_names`) is still the
        # store, and with a reader or a mutating verb it is a read or a destruction
        # attempt. A bare mention (listing the plugin directory, reading its source)
        # stays allowed.
        return _BLOCK_READ.format(what="secret store")
    if _HERMES_HOME_TEXT_RE.search(text) and _MUTATING_RE.search(text):
        # A mutating command aimed at the Hermes home can erase or copy out the store
        # without ever spelling its name.
        return _BLOCK_READ.format(what="the secret store directory")
    return None


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
    """Values eligible for scrubbing, loaded once per call. Never log these.

    Both the values the user stored through this plugin and credential-shaped entries
    that Hermes itself wrote to the profile ``.env`` become needles, so a provider key
    is scrubbed even though it was never indexed by name.

    Raises when the store cannot be read: callers turn that into withheld output, so a
    failure never silently disables scrubbing.
    """
    from hermes_cli.config import load_env

    values = set(_drop.persisted_secret_values())
    env = load_env()
    if isinstance(env, dict):
        for name, value in env.items():
            if isinstance(value, str) and value and _CREDENTIAL_NAME_RE.search(str(name)):
                values.add(value)
    if not values and _drop.stored_secret_names():
        # The name index lists secrets but no value could be resolved: the store is
        # there but unreadable, or values were removed behind the plugin's back.
        # Scrubbing would silently become a no-op, so fail closed instead.
        raise OSError("secret store lists names but yielded no values")
    return [value for value in values if _drop.registers_for_redaction(value)]


def scrub_text(
    text: str,
    values: list[str] | None = None,
    *,
    injected: list[str] | None = None,
) -> str:
    """Replace stored values and their common encodings with ``REDACTED``.

    *injected* holds values that were substituted into this call. They are scrubbed
    even when `registers_for_redaction` would skip them, because for this call's output
    an exact leak of a short or word-like value is still a leak.
    """
    if not isinstance(text, str) or not text:
        return text
    needles: set[str] = set()
    names = load_secret_values() if values is None else values
    needles.update(encoded_variants(names))
    if injected:
        needles.update(encoded_variants(injected, force=True))
    for needle in sorted(needles, key=len, reverse=True):
        if needle in text:
            text = text.replace(needle, REDACTED)
    return text


def encoded_variants(values: list[str], *, force: bool = False) -> list[str]:
    """Every needle to remove for *values*, longest first, duplicates dropped.

    Unless *force* is set, no needle is emitted for a value that
    ``registers_for_redaction`` rejects (short values and plain words would rewrite
    ordinary text).
    """
    needles: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if not force and not _drop.registers_for_redaction(value):
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
