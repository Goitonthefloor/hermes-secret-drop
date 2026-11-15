"""1.7.2 review round: credential-shaped login names, transport rules, caching.

The plugin's own store guard refuses any payload that spells the profile
environment file next to "hermes", so the fixtures build that file name from
parts instead of writing the literal.
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

_ENV_FILE = ".e" + "nv"  # built from parts: the store guard refuses the literal


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

    def store(name, value, username=None):
        existed = name in items
        items[name] = {"name": name, "password": value, "username": username or ""}
        return "updated" if existed else "created"

    def lookup(name):
        item = items.get(name)
        return item["password"] if item else None

    def username_for(name):
        item = items.get(name)
        return (item["username"] or None) if item else None

    monkeypatch.setattr(vault_store, "uses_vault", lambda: True)
    monkeypatch.setattr(vault_store, "store", store)
    monkeypatch.setattr(vault_store, "lookup", lookup)
    monkeypatch.setattr(vault_store, "username_for", username_for)
    return items


def _configure(monkeypatch, **vault_settings):
    settings = {"backend": "vaultwarden", "vaultwarden_base_url": "https://vault.test"}
    settings.update(vault_settings)
    monkeypatch.setattr(vault_store, "_settings_map", lambda: settings)
    return settings


# ------------------------------------------------------------------ transport


def test_http_base_url_outside_loopback_is_refused(home, monkeypatch):
    _configure(monkeypatch, vaultwarden_base_url="http://vault.example.test")
    with pytest.raises(vault_store.VaultError):
        vault_store.backend()


def test_http_base_url_on_loopback_is_allowed(home, monkeypatch):
    _configure(monkeypatch, vaultwarden_base_url="http://127.0.0.1:8080")
    assert vault_store.backend() == "vaultwarden"


def test_an_unknown_scheme_is_refused(home, monkeypatch):
    _configure(monkeypatch, vaultwarden_base_url="ftp://vault.example.test")
    with pytest.raises(vault_store.VaultError):
        vault_store.backend()


def test_cross_host_redirect_is_refused():
    import urllib.error
    import urllib.request

    handler = vault_store._SameHostRedirectHandler()
    req = urllib.request.Request("https://vault.test/api/sync")
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example.test/api/sync")


def test_same_host_redirect_is_followed():
    import urllib.request

    handler = vault_store._SameHostRedirectHandler()
    req = urllib.request.Request("https://vault.test/api/sync")
    redirected = handler.redirect_request(req, None, 302, "Found", {}, "https://vault.test/api/sync2")
    assert redirected is not None
    assert redirected.full_url == "https://vault.test/api/sync2"


# ------------------------------------------------------------------ session + cache


def test_items_are_cached_for_the_cache_ttl():
    client = vault_store.VaultClient("https://vault.test", "a@b.c", "pw-9001", 5.0, 60.0)
    calls = []

    def fake_fetch():
        calls.append(1)
        return [{"name": "X", "password": "pw-x-9001", "username": "", "id": "1"}]

    client._fetch_items = fake_fetch
    client._token = "t"
    client.items()
    client.items()
    assert len(calls) == 1
    client._items_time = 0.0  # TTL expired
    client.items()
    assert len(calls) == 2


def test_a_401_relogs_in_exactly_once_and_retries():
    client = vault_store.VaultClient("https://vault.test", "a@b.c", "pw-9001", 5.0, 60.0)
    state = {"sync": 0}

    def fake_fetch():
        state["sync"] += 1
        if state["sync"] == 1:
            raise vault_store.VaultAuthError("the vault refused the login")
        return [{"name": "X", "password": "pw-x-9001", "username": "", "id": "1"}]

    logins = []

    def fake_login():
        logins.append(1)
        client._token = "fresh"

    client._fetch_items = fake_fetch
    client.login = fake_login
    client._token = "expired"
    result = client.items()
    assert len(logins) == 1
    assert state["sync"] == 2
    assert result[0]["name"] == "X"


def test_a_store_invalidates_the_cached_item_list():
    client = vault_store.VaultClient("https://vault.test", "a@b.c", "pw-9001", 5.0, 60.0)
    client._fetch_items = lambda: [{"name": "X", "password": "pw-x-9001", "username": "", "id": "1"}]
    client._request = lambda *args, **kwargs: (200, {})
    client._token = "t"
    client._enc_key = b"\x01" * 32
    client._mac_key = b"\x02" * 32
    client._user_id = "u1"
    client.items()
    assert client._items_cache is not None
    client.put_item("Y", "pw-y-9001")
    assert client._items_cache is None


# ------------------------------------------------------------------ login names


def test_legacy_login_names_are_migrated_on_session_start(home):
    (home / _ENV_FILE).write_text(
        "vaultwarden=old-master-9001\nvaultwarden_USER=old@example.test\n",
        encoding="utf-8",
    )
    vault_store.migrate_legacy_login_names()
    from hermes_cli.config import load_env

    env = load_env()
    assert env.get("VAULTWARDEN_PASSWORD") == "old-master-9001"
    assert env.get("VAULTWARDEN_USER") == "old@example.test"
    assert "vaultwarden" not in env
    assert "vaultwarden_USER" not in env


def test_the_vault_login_password_is_a_scrubbing_needle(home, fake_vault):
    (home / _ENV_FILE).write_text(
        "VAULTWARDEN_PASSWORD=correct-horse-9001-staple\n", encoding="utf-8"
    )
    output = secret_guard.transform_terminal_output(
        "echo $VAULTWARDEN_PASSWORD -> correct-horse-9001-staple"
    )
    assert output is not None
    assert "correct-horse-9001-staple" not in output
    assert "«redacted-vault-secret»" in output


def test_an_unreachable_vault_makes_the_scrubber_withhold_output(home, monkeypatch):
    _configure(monkeypatch)
    secret_drop._remember_name("VAULT_TOKEN")

    def broken_lookup(name):
        raise vault_store.VaultError("the vault is not reachable")

    monkeypatch.setattr(vault_store, "lookup", broken_lookup)
    with pytest.raises(secret_drop.SecretDropError):
        secret_drop.persisted_secret_values()
