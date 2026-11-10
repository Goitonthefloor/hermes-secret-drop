"""The optional username that can be entered next to a secret.

A username is stored as ``<NAME>_USER``. It is injectable through an alias like any
stored name, but it is an account name, not a credential, so it is never used as an
output needle.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from secret_drop import (
    SecretDropError,
    accept_secret_file,
    is_account_name,
    stored_secret_names,
)
from secret_guard import REDACTED, pre_tool_call, scrub_text

ENV_FILE = "." + "env"


@pytest.fixture
def home(tmp_path, monkeypatch):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    from hermes_cli.config import invalidate_env_cache

    invalidate_env_cache()
    return hermes


def test_username_is_stored_next_to_the_secret(home):
    result = accept_secret_file("DEPLOY_PASSWORD", "s3cret-value-9001", "deploy-bot")
    assert result["username_stored_as"] == "DEPLOY_PASSWORD_USER"
    assert result["stored_as"] == "DEPLOY_PASSWORD"
    from hermes_cli.config import load_env

    env = load_env()
    assert env["DEPLOY_PASSWORD_USER"] == "deploy-bot"
    assert env["DEPLOY_PASSWORD"] == "s3cret-value-9001"
    assert stored_secret_names() == ["DEPLOY_PASSWORD", "DEPLOY_PASSWORD_USER"]


def test_username_is_optional_and_blank_counts_as_absent(home):
    assert accept_secret_file("DEPLOY_PASSWORD", "s3cret-value-9001")["username_stored_as"] is None
    from hermes_cli.config import invalidate_env_cache

    invalidate_env_cache()
    blank = accept_secret_file("OTHER_PASSWORD", "s3cret-value-9002", "   ")
    assert blank["username_stored_as"] is None
    assert stored_secret_names() == ["DEPLOY_PASSWORD", "OTHER_PASSWORD"]


def test_invalid_username_is_refused_before_anything_is_stored(home):
    for bad in ("line\nbreak", "ümlaut", "x" * 300):
        with pytest.raises(SecretDropError):
            accept_secret_file("DEPLOY_PASSWORD", "s3cret-value-9001", bad)
    env_file = home / ENV_FILE
    assert not env_file.exists() or "DEPLOY_PASSWORD=" not in env_file.read_text()


def test_username_alias_is_injectable(home):
    accept_secret_file("DEPLOY_PASSWORD", "s3cret-value-9001", "deploy-bot")
    result = pre_tool_call(
        tool_name="terminal",
        args={
            "command": (
                "curl -u {{secret:DEPLOY_PASSWORD_USER}}:{{secret:DEPLOY_PASSWORD}} "
                "https://example.test"
            )
        },
    )
    assert result is not None and result["action"] == "modify"
    command = result["args"]["command"]
    assert "deploy-bot:s3cret-value-9001" in command


def test_username_is_never_an_output_needle(home):
    """Scrubbing an account name would rewrite every mention of it."""
    accept_secret_file("DEPLOY_PASSWORD", "s3cret-value-9001", "deploy-bot")
    cleaned = scrub_text("user deploy-bot connected with s3cret-value-9001")
    assert "deploy-bot" in cleaned
    assert "s3cret-value-9001" not in cleaned
    assert REDACTED in cleaned


def test_a_secret_stored_under_a_user_name_is_still_scrubbed(home):
    """The suffix alone does not make a name an account name."""
    result = accept_secret_file("DEPLOY_USER", "s3cret-value-9001")
    assert result["redacted"] is True
    assert is_account_name("DEPLOY_USER") is False
    assert scrub_text("s3cret-value-9001") == REDACTED


def test_only_a_name_this_plugin_wrote_as_a_username_is_an_account_name(home):
    assert is_account_name("DEPLOY_PASSWORD_USER") is False
    accept_secret_file("DEPLOY_PASSWORD", "s3cret-value-9001", "deploy-bot")
    assert is_account_name("DEPLOY_PASSWORD_USER") is True
    assert is_account_name("DEPLOY_USER") is False
    assert is_account_name("DEPLOY_PASSWORD") is False


def test_a_secret_stored_over_a_generated_username_name_is_scrubbed(home):
    accept_secret_file("DEPLOY_PASSWORD", "s3cret-value-9001", "deploy-bot")
    accept_secret_file("DEPLOY_PASSWORD_USER", "s3cret-value-9002")
    assert is_account_name("DEPLOY_PASSWORD_USER") is False
    cleaned = scrub_text("s3cret-value-9002 then s3cret-value-9001")
    assert "s3cret-value-9002" not in cleaned
    assert "s3cret-value-9001" not in cleaned


def test_the_account_index_is_part_of_the_guarded_store(home):
    from secret_drop import account_index_path

    path = account_index_path()
    checked = (
        ("read_file", {"path": str(path)}),
        ("write_file", {"path": str(path), "content": "DEPLOY_PASSWORD\n"}),
    )
    for tool, args in checked:
        result = pre_tool_call(tool_name=tool, args=args)
        assert result is not None and result["action"] == "block", tool
