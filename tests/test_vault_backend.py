"""The optional Vaultwarden backend: configuration gate, store, alias resolution.

No network here: the vault client is replaced by a fake that keeps items in a dict.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import secret_drop  # noqa: E402
import secret_guard  # noqa: E402
import vault_store  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    return hermes


@pytest.fixture
def fake_vault(monkeypatch):
    """A vault without a network: items live in a dict."""
    items: dict[str, dict] = {}
    calls: list[tuple] = []

    def store(name, value, username=None):
        calls.append(("store", name))
        items[name] = {"name": name, "password": value, "username": username or ""}
        return "created" if name not in items else "updated"

    def lookup(name):
        calls.append(("lookup", name))
        item = items.get(name)
        return item["password"] if item else None

    def username_for(name):
        calls.append(("username_for", name))
        item = items.get(name)
        return (item["username"] or None) if item else None

    monkeypatch.setattr(vault_store, "uses_vault", lambda: True)
    monkeypatch.setattr(vault_store, "store", store)
    monkeypatch.setattr(vault_store, "lookup", lookup)
    monkeypatch.setattr(vault_store, "username_for", username_for)
    return items, calls


def _configure(monkeypatch, **vault_settings):
    settings = {"backend": "vaultwarden", "vaultwarden_base_url": "https://vault.test"}
    settings.update(vault_settings)
    monkeypatch.setattr(vault_store, "_settings_map", lambda: settings)
    return settings


# ------------------------------------------------------------------ configuration gate


def test_default_backend_is_the_file_store(home):
    assert vault_store.backend() == "file"
    assert vault_store.uses_vault() is False


def test_backend_needs_a_vault_url(home, monkeypatch):
    monkeypatch.setattr(vault_store, "_settings_map", lambda: {"backend": "vaultwarden"})
    assert vault_store.backend() == "file"


def test_configured_backend_is_vaultwarden(home, monkeypatch):
    _configure(monkeypatch)
    assert vault_store.backend() == "vaultwarden"


def test_the_manifest_declares_the_settings_the_hub_renders(home):
    """The Desktop plugins hub builds its form from ``config_schema``; the code reads those keys."""
    from utils import fast_safe_load

    manifest = fast_safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8")) or {}
    schema = manifest.get("config_schema") or {}
    assert schema["backend"]["choices"] == ["file", "vaultwarden"]
    assert schema["vaultwarden_base_url"]["type"] == "str"
    assert schema["vaultwarden_email"]["secret"] is True
    assert schema["vaultwarden_email"]["env"] == vault_store._EMAIL_ENV
    assert schema["vaultwarden_password"]["env"] == vault_store._PASSWORD_ENV


# ------------------------------------------------------------------ storing


def test_stored_secret_lands_in_the_vault_not_the_env_file(home, fake_vault):
    items, _calls = fake_vault
    result = secret_drop.accept_secret_file("VAULT_TOKEN", "s3cret-value-9001", "hermes")
    assert result["backend"] == "vaultwarden"
    assert items["VAULT_TOKEN"]["password"] == "s3cret-value-9001"
    assert items["VAULT_TOKEN"]["username"] == "hermes"
    assert "VAULT_TOKEN" in secret_drop.stored_secret_names()

    from hermes_cli.config import load_env

    assert "VAULT_TOKEN" not in load_env()


def test_username_of_a_vault_item_is_injectable(home, fake_vault):
    fake_vault[0]["VAULT_TOKEN"] = {"name": "VAULT_TOKEN", "password": "s3cret-value-9001", "username": "hermes"}
    secret_drop._remember_account_name("VAULT_TOKEN_USER")
    secret_drop._remember_name("VAULT_TOKEN_USER")
    secret_drop._remember_name("VAULT_TOKEN")
    assert secret_drop.stored_secret_value("VAULT_TOKEN_USER") == "hermes"
    assert secret_drop.stored_secret_value("VAULT_TOKEN") == "s3cret-value-9001"


def test_vault_refusal_is_reported_without_the_value(home, fake_vault, monkeypatch):
    def broken_store(name, value, username=None):
        raise vault_store.VaultError("the vault is not reachable")

    monkeypatch.setattr(vault_store, "store", broken_store)
    with pytest.raises(secret_drop.SecretDropError) as excinfo:
        secret_drop.accept_secret_file("VAULT_TOKEN", "s3cret-value-9001")
    assert "s3cret-value-9001" not in str(excinfo.value)


# ------------------------------------------------------------------ alias resolution


def test_alias_resolves_from_the_vault(home, fake_vault):
    fake_vault[0]["VAULT_TOKEN"] = {"name": "VAULT_TOKEN", "password": "s3cret-value-9001", "username": ""}
    secret_drop._remember_name("VAULT_TOKEN")
    resolved, error = secret_guard.substitute_aliases("curl -H 'x: {{secret:VAULT_TOKEN}}'")
    assert error is None
    assert resolved == "curl -H 'x: s3cret-value-9001'"


def test_unreachable_vault_blocks_the_alias(home, fake_vault, monkeypatch):
    def broken_lookup(name):
        raise vault_store.VaultError("the vault is not reachable")

    monkeypatch.setattr(vault_store, "lookup", broken_lookup)
    secret_drop._remember_name("VAULT_TOKEN")
    resolved, error = secret_guard.substitute_aliases("curl -H 'x: {{secret:VAULT_TOKEN}}'")
    assert resolved is None
    assert "did not answer" in error
    assert "VAULT_TOKEN" in error


def test_an_indexed_name_without_a_value_anywhere_is_blocked_as_empty(home, fake_vault):
    secret_drop._remember_name("VAULT_MISSING")
    resolved, error = secret_guard.substitute_aliases("echo {{secret:VAULT_MISSING}}")
    assert resolved is None
    assert "is empty" in error


def test_redaction_needles_come_from_the_vault(home, fake_vault):
    fake_vault[0]["VAULT_TOKEN"] = {"name": "VAULT_TOKEN", "password": "s3cret-value-9001", "username": ""}
    secret_drop._remember_name("VAULT_TOKEN")
    assert "s3cret-value-9001" in secret_drop.persisted_secret_values()


# ------------------------------------------------------------------ crypto helpers


def test_encrypt_decrypt_round_trip():
    import os

    enc_key, mac_key = os.urandom(32), os.urandom(32)
    encrypted = vault_store._encrypt("hunter2-value", enc_key, mac_key)
    assert encrypted.startswith("2.")
    assert vault_store._decrypt(encrypted, enc_key, mac_key) == b"hunter2-value"


def test_tampered_enc_string_is_refused():
    import os

    enc_key, mac_key = os.urandom(32), os.urandom(32)
    encrypted = vault_store._encrypt("hunter2-value", enc_key, mac_key)
    kind, payload = encrypted.split(".", 1)
    iv, ct, mac = payload.split("|")
    tampered = f"{kind}.{iv}|{ct[:-4]}AAAA|{mac}"
    with pytest.raises(vault_store.VaultError):
        vault_store._decrypt(tampered, enc_key, mac_key)
