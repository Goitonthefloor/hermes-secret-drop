"""Alias isolation: the value stays in the gateway, out of the model context."""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from secret_drop import SecretDropError, accept_secret_file, _public_error
from secret_guard import (
    REDACTED,
    encoded_variants,
    guard_store_access,
    pre_tool_call,
    scrub_text,
    substitute_aliases,
    transform_terminal_output,
    transform_tool_result,
)

SECRET = "S3cret-Value-9001"


@pytest.fixture
def home(tmp_path, monkeypatch):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    import secret_guard

    secret_guard._INJECTED.clear()
    return hermes


@pytest.fixture
def stored(home):
    accept_secret_file("DEPLOY_PASSWORD", SECRET)
    return home


def _blocked(result) -> str:
    assert result is not None and result["action"] == "block"
    return result["message"]


# ── alias substitution ──────────────────────────────────────────────


def test_alias_is_replaced_in_terminal_arguments_only(stored):
    result = pre_tool_call(
        tool_name="terminal",
        args={"command": "curl -u admin:{{secret:DEPLOY_PASSWORD}} https://example.test"},
    )
    assert result == {
        "action": "modify",
        "args": {"command": "curl -u admin:S3cret-Value-9001 https://example.test"},
    }
    # The block path (the only text the model could see) never carries the value.
    unknown = pre_tool_call(tool_name="terminal", args={"command": "{{secret:NOPE}}"})
    assert SECRET not in _blocked(unknown)


def test_alias_is_replaced_in_execute_code(stored):
    result = pre_tool_call(
        tool_name="execute_code",
        args={"code": "token = '{{secret:DEPLOY_PASSWORD}}'\nprint(token[:2])"},
    )
    assert result["action"] == "modify"
    assert result["args"]["code"] == "token = 'S3cret-Value-9001'\nprint(token[:2])"


def test_command_without_alias_is_untouched(stored):
    assert pre_tool_call(tool_name="terminal", args={"command": "ls -la"}) is None
    assert pre_tool_call(tool_name="read_file", args={"path": "notes.txt"}) is None


def test_unknown_alias_blocks_without_the_value(stored):
    result = pre_tool_call(tool_name="terminal", args={"command": "echo {{secret:MISSING_ONE}}"})
    message = _blocked(result)
    assert "{{secret:MISSING_ONE}}" in message
    assert SECRET not in message


def test_empty_value_blocks(home):
    accept_secret_file("EMPTY_SECRET", "placeholder-0001")
    env = home / ".env"
    env.write_text("EMPTY_SECRET=\n")
    from hermes_cli.config import invalidate_env_cache

    invalidate_env_cache()
    result = pre_tool_call(tool_name="terminal", args={"command": "echo {{secret:EMPTY_SECRET}}"})
    assert "empty" in _blocked(result).lower()


def test_invalid_alias_name_blocks(stored):
    result = pre_tool_call(tool_name="terminal", args={"command": "echo {{secret:bad-name}}"})
    assert "not a valid secret alias" in _blocked(result)


def test_provider_credential_is_not_injectable(home):
    accept_secret_file("OPENAI_API_KEY", "sk-test-000000000000")
    result = pre_tool_call(tool_name="terminal", args={"command": "echo {{secret:OPENAI_API_KEY}}"})
    assert "provider credential" in _blocked(result)


def test_substitute_aliases_reports_status_without_leaking(stored):
    resolved, error = substitute_aliases("a {{secret:DEPLOY_PASSWORD}} b")
    assert resolved == f"a {SECRET} b" and error is None
    resolved, error = substitute_aliases("{{secret:UNKNOWN}}")
    assert resolved is None and SECRET not in (error or "")


# ── read guard ──────────────────────────────────────────────────────


def test_read_file_on_env_is_blocked(stored):
    message = guard_store_access("read_file", {"path": str(stored / ".env")})
    assert message and "{{secret:NAME}}" in message
    assert guard_store_access("read_file", {"path": str(stored / "secret-drop-names")})
    assert guard_store_access("read_file", {"path": str(stored / "secret-drops" / "x")})


def test_search_files_on_store_is_blocked(stored):
    assert guard_store_access("search_files", {"path": str(stored), "pattern": r"\.env"})
    assert guard_store_access("search_files", {"path": str(stored / ".env"), "pattern": "X"})


def test_terminal_reader_on_env_is_blocked(stored):
    for command in (
        f"cat {stored}/.env",
        "cat $HERMES_HOME/.env",
        "grep -R DEPLOY ~/.hermes/.env",
        "base64 $HERMES_HOME/secret-drop-names",
        "python3 -c \"print(open('$HERMES_HOME/.env').read())\"",
    ):
        message = guard_store_access("terminal", {"command": command})
        assert message, command


def test_execute_code_reading_the_store_is_blocked(stored):
    code = f"print(open('{stored}/secret-drops/x').read())"
    assert guard_store_access("execute_code", {"code": code})


def test_harmless_commands_pass_the_guard(stored):
    assert guard_store_access("terminal", {"command": "git status --short"}) is None
    assert guard_store_access("terminal", {"command": "echo hello > /tmp/out.txt"}) is None
    assert guard_store_access("execute_code", {"code": "print(1 + 1)"}) is None
    assert guard_store_access("read_file", {"path": str(stored / "config.yaml")}) is None


# ── output scrubber ─────────────────────────────────────────────────


def _encodings(value: str) -> set[str]:
    raw = value.encode()
    forms = {
        value,
        value[::-1],
        raw.hex(),
        raw.hex().upper(),
        quote(value, safe=""),
        quote_plus(value, safe=""),
        base64.b64encode(raw).decode(),
        base64.urlsafe_b64encode(raw).decode(),
        " ".join(value),
        ".".join(value),
        "#".join(value),
    }
    return {form for form in forms if form}


def test_every_encoding_is_replaced(stored):
    for form in _encodings(SECRET):
        cleaned = scrub_text(f"before {form} after")
        assert form not in cleaned, form
        assert REDACTED in cleaned


def test_base64_variants_without_padding_are_replaced():
    value = "???-secret-01"
    raw = value.encode()
    standard = base64.b64encode(raw).decode()
    urlsafe = base64.urlsafe_b64encode(raw).decode()
    assert standard != urlsafe
    for form in (standard, standard.rstrip("="), urlsafe, urlsafe.rstrip("=")):
        cleaned = scrub_text(f"[{form}]", [value])
        assert form not in cleaned, form
        assert REDACTED in cleaned


def test_plain_text_and_short_values_survive(stored):
    values = ["abcdefgh"]
    assert scrub_text("abcdefgh is a normal word here", values) == "abcdefgh is a normal word here"
    assert scrub_text("deployment finished", [SECRET]) == "deployment finished"
    assert encoded_variants(["abcdefgh"]) == []


def test_hooks_scrub_terminal_output_and_tool_results(stored):
    terminal = transform_terminal_output(output=f"token={SECRET}\n", command="curl ...")
    assert terminal is not None and SECRET not in terminal and REDACTED in terminal
    assert transform_terminal_output(output="nothing to hide", command="ls") is None

    result = transform_tool_result(
        tool_name="read_file", args={"path": "notes.txt"}, result=f"file says {SECRET}"
    )
    assert result is not None and SECRET not in result
    assert transform_tool_result(tool_name="read_file", args={}, result="fine") is None


def test_variants_are_sorted_longest_first(stored):
    variants = encoded_variants([SECRET])
    assert variants == sorted(variants, key=len, reverse=True)
    assert len(variants) == len(set(variants))


# ── public error text ───────────────────────────────────────────────


def test_public_error_hides_host_details_and_the_value(caplog):
    with caplog.at_level("WARNING"):
        assert _public_error(RuntimeError(f"backend rejected {SECRET}"), SECRET) == (
            "could not store secret"
        )
        assert _public_error(RuntimeError("disk full at /srv/app/.env"), "") == (
            "could not store secret"
        )
    assert SECRET not in caplog.text
    assert "disk full" in caplog.text


def test_failed_store_returns_only_the_generic_message(home, monkeypatch):
    def boom(key, value):
        raise RuntimeError("backend rejected the write")

    monkeypatch.setattr("hermes_cli.config.save_env_value_secure", boom)
    with pytest.raises(SecretDropError) as caught:
        accept_secret_file("MY_APP_PASSWORD", SECRET)
    assert str(caught.value) == "could not store secret"


# ── drop route body cap ─────────────────────────────────────────────


class _ChunkedRequest:
    def __init__(self, chunks: list[bytes], consumed: list[int] | None = None):
        self.headers: dict[str, str] = {}
        self._chunks = chunks
        self._consumed = consumed

    async def stream(self):
        for chunk in self._chunks:
            if self._consumed is not None:
                self._consumed[0] += 1
            yield chunk


def test_chunked_body_over_cap_is_rejected_early():
    pytest.importorskip("fastapi")
    from fastapi import HTTPException

    from dashboard.plugin_api import drop

    consumed = [0]
    request = _ChunkedRequest([b"x" * 20_000 for _ in range(5)], consumed)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(drop(request))
    assert caught.value.status_code == 413
    assert consumed[0] < 5  # aborted as soon as the cap was crossed


def test_chunked_body_over_cap_is_rejected_by_http(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dashboard import plugin_api

    called: list[str] = []
    monkeypatch.setattr(
        plugin_api, "accept_secret_for_profile",
        lambda name, value, profile: called.append(name) or {"success": True},
    )
    app = FastAPI()
    app.include_router(plugin_api.router, prefix="/api/plugins/secret-drop")
    client = TestClient(app)

    def body():
        for _ in range(4):
            yield b"y" * 20_000

    response = client.post("/api/plugins/secret-drop/drop", content=body())
    assert response.status_code == 413
    assert called == []
    assert "y" * 20_000 not in response.text


# ── regression: findings from the change review ─────────────────────


def test_value_injected_into_a_call_is_scrubbed_even_when_word_like(home):
    """A short or word-like value skips the global needles but not its own call."""
    accept_secret_file("SHORT_PIN", "hunter")

    call_id = "call-short-1"
    result = pre_tool_call(
        tool_name="terminal",
        args={"command": "echo {{secret:SHORT_PIN}}"},
        tool_call_id=call_id,
    )
    assert result is not None and result["action"] == "modify"
    cleaned = transform_terminal_output(output="hunter\n", tool_call_id=call_id)
    assert cleaned is not None and "hunter" not in cleaned
    # A different call with no injection keeps ordinary words intact.
    assert transform_terminal_output(output="hunter\n", tool_call_id="call-other") is None


def test_injection_without_a_call_id_still_gets_scrubbed(home):
    """A dispatch path that carries no tool_call_id must not drop the substitution."""
    accept_secret_file("SHORT_PIN", "hunter")
    result = pre_tool_call(tool_name="terminal", args={"command": "echo {{secret:SHORT_PIN}}"})
    assert result is not None and result["action"] == "modify"
    cleaned = transform_terminal_output(output="hunter\n")
    assert cleaned is not None and "hunter" not in cleaned


def test_moving_or_deleting_the_store_is_blocked(stored):
    """Relocating the store would leave the scrubber without needles."""
    for command in (
        "mv ~/.hermes/.env /tmp/x",
        "rm -f ~/.hermes/.env",
        "cp ~/.hermes/secret-drop-names /tmp/names",
        "truncate -s 0 ~/.hermes/.env",
    ):
        assert guard_store_access("terminal", {"command": command}), command


def test_a_quoted_reader_is_blocked(stored):
    assert guard_store_access("terminal", {"command": "sh -c 'cat ~/.hermes/.env'"})
    assert guard_store_access("terminal", {"command": 'bash -c "head -5 ~/.hermes/.env"'})


def test_provider_key_in_the_env_is_scrubbed_without_being_indexed(stored):
    """Values Hermes wrote itself are credentials too, even with no name index entry."""
    key = "sk-live-0123456789abcdef"
    env_file = stored / ".env"
    env_file.write_text(env_file.read_text() + f"PROVIDER_API_KEY={key}\n")
    cleaned = scrub_text(f"request failed with key {key} in header")
    assert key not in cleaned


def test_scrubber_fails_closed_when_the_store_cannot_be_read(monkeypatch):
    import secret_guard

    def boom() -> list[str]:
        raise OSError("store unreadable")

    monkeypatch.setattr(secret_guard, "load_secret_values", boom)
    withheld = transform_terminal_output(output="anything")
    assert withheld is not None and "withheld" in withheld
    withheld = transform_tool_result(result="anything")
    assert withheld is not None and "withheld" in withheld


def test_search_over_the_home_directory_is_blocked(stored):
    assert guard_store_access("search_files", {"path": str(stored), "pattern": "PASSWORD"})
    assert guard_store_access("search_files", {"path": str(stored), "pattern": "x"})

