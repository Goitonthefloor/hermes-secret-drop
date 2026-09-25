"""The secret file drop stores a value without echoing it, then deletes the file."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from secret_drop import SecretDropError, accept_secret_file, command_name_token, messaging_secret_reply


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def home(tmp_path, monkeypatch):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    return hermes


def test_command_name_token_discards_inline_secrets():
    assert command_name_token("/secret") == ("", False)
    assert command_name_token("DEPLOY_PASSWORD") == ("DEPLOY_PASSWORD", False)
    assert command_name_token("DEPLOY_PASSWORD hunter2") == ("", True)
    assert command_name_token("DEPLOY_PASSWORD=hunter2") == ("", True)


def test_messaging_reply_does_not_echo_the_argument():
    planted = "hunter2-do-not-echo"
    reply = messaging_secret_reply(f"DEPLOY_PASSWORD {planted}")
    assert planted not in reply
    assert "Nothing was stored" in reply
    bare = messaging_secret_reply("")
    assert "Desktop" in bare


def test_accept_writes_env_then_deletes_the_file(home):
    secret = "s3cret-value-9001"
    result = accept_secret_file("DEPLOY_PASSWORD", secret)
    assert result["success"] is True
    assert result["stored_as"] == "DEPLOY_PASSWORD"
    assert result["passthrough"] is True
    assert secret not in repr(result)

    env_text = (home / ".env").read_text()
    assert "DEPLOY_PASSWORD=" in env_text
    assert _digest(secret) == _digest(
        next(
            line.split("=", 1)[1].strip().strip('"')
            for line in env_text.splitlines()
            if line.startswith("DEPLOY_PASSWORD=")
        )
    )
    assert list((home / "secret-drops").iterdir()) == []
    names = (home / "secret-drop-names").read_text()
    assert names.strip() == "DEPLOY_PASSWORD"
    assert secret not in names
    assert secret not in (home / "config.yaml").read_text()

    from agent.redact import redact_sensitive_text

    visible = redact_sensitive_text(f"the password is {secret}")
    assert secret not in visible


def test_provider_credential_is_stored_but_not_passed_through(home):
    secret = "sk-provider-secret"
    result = accept_secret_file("OPENAI_API_KEY", secret)
    assert result["passthrough"] is False
    assert secret not in repr(result)
    assert list((home / "secret-drops").iterdir()) == []


def test_failure_still_deletes_the_file(home, monkeypatch):
    secret = "wipe-me-please"

    def boom(key, value):
        raise RuntimeError(f"backend rejected {value}")

    monkeypatch.setattr("hermes_cli.config.save_env_value_secure", boom)
    with pytest.raises(SecretDropError) as caught:
        accept_secret_file("MY_APP_PASSWORD", secret)
    assert secret not in str(caught.value)
    assert list((home / "secret-drops").iterdir()) == []


def test_symlink_drop_dir_is_refused(home):
    outside = home.parent / "elsewhere"
    outside.mkdir()
    os.symlink(outside, home / "secret-drops")
    with pytest.raises(SecretDropError):
        accept_secret_file("MY_APP_PASSWORD", "not-written")
    assert list(outside.iterdir()) == []


def test_rejects_empty_newlines_and_denylisted_names(home):
    with pytest.raises(SecretDropError):
        accept_secret_file("MY_APP_PASSWORD", "")
    with pytest.raises(SecretDropError):
        accept_secret_file("MY_APP_PASSWORD", "line\nbreak")
    with pytest.raises(SecretDropError):
        accept_secret_file("PATH", "not-allowed")
