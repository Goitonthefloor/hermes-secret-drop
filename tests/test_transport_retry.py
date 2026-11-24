"""Transport robustness of the Vaultwarden client.

The reported failure mode: a one-second network hiccup (proxy reload, vault container
restart) turned into ``VaultError("the vault is not reachable")`` on the first try and the
fail-closed scrubber withheld every tool result. These tests pin the retry, the breaker
and the diagnostic message, and that a *store* request is never repeated.
"""

from __future__ import annotations

import email.message
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import vault_store  # noqa: E402

PASSWORD = "s3cret-value-9001"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Never read the operator's real configuration from a test."""
    monkeypatch.setattr(vault_store, "_settings_map", lambda: {})
    monkeypatch.setattr(vault_store.time, "sleep", lambda _s: None)


class FakeResponse:
    status = 200

    def __init__(self, body: bytes = b'{"ok": true}') -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Fails the first *failures* calls, then answers. ``None`` never recovers."""

    def __init__(self, failures: int | None, body: bytes = b'{"ok": true}') -> None:
        self.failures = failures
        self.body = body
        self.calls = 0
        self.timeouts: list[float | None] = []

    def open(self, request, timeout=None):
        self.calls += 1
        self.timeouts.append(timeout)
        if self.failures is None or self.calls <= self.failures:
            raise urllib.error.URLError("[Errno 111] Connection refused")
        return FakeResponse(self.body)


def make_client(**kwargs) -> vault_store.VaultClient:
    return vault_store.VaultClient(
        base_url="https://vault.example.test",
        email="probe@example.test",
        password=PASSWORD,
        timeout=kwargs.pop("timeout", 20.0),
        **kwargs,
    )


def use_opener(monkeypatch, opener: FakeOpener) -> FakeOpener:
    monkeypatch.setattr(vault_store, "_SAFE_OPENER", opener)
    return opener


def test_a_transient_transport_failure_is_retried(monkeypatch):
    opener = use_opener(monkeypatch, FakeOpener(failures=1))
    status, body = make_client()._request("/api/sync")

    assert status == 200
    assert body == {"ok": True}
    assert opener.calls == 2, "the second attempt has to happen after one URLError"


def test_every_attempt_uses_a_shorter_timeout_than_the_first(monkeypatch):
    opener = use_opener(monkeypatch, FakeOpener(failures=2))
    make_client(timeout=20.0)._request("/api/sync")

    assert opener.timeouts[0] == 20.0
    assert all(t is not None and t <= 8.0 for t in opener.timeouts[1:])


def test_a_permanent_failure_names_the_reason_and_the_attempts(monkeypatch):
    opener = use_opener(monkeypatch, FakeOpener(failures=None))
    with pytest.raises(vault_store.VaultError) as excinfo:
        make_client()._request("/api/sync")

    message = str(excinfo.value)
    assert "the vault is not reachable after 3 attempt(s)" in message
    assert "Connection refused" in message, "the URLError reason must not be swallowed"
    assert opener.calls == 3


def test_the_reason_reaches_the_log(monkeypatch, caplog):
    use_opener(monkeypatch, FakeOpener(failures=None))
    with caplog.at_level("WARNING"):
        with pytest.raises(vault_store.VaultError):
            make_client()._request("/api/sync")

    assert "vaultwarden transport failed on /api/sync after 3 attempt(s)" in caplog.text
    assert "Connection refused" in caplog.text


def test_the_breaker_stops_further_attempts_while_the_vault_is_down(monkeypatch):
    opener = use_opener(monkeypatch, FakeOpener(failures=None))
    client = make_client()
    with pytest.raises(vault_store.VaultError):
        client._request("/api/sync")
    calls_after_first = opener.calls

    with pytest.raises(vault_store.VaultError) as excinfo:
        client._request("/api/ciphers")

    assert opener.calls == calls_after_first, "the breaker must not touch the network"
    assert "not retrying for another" in str(excinfo.value)


def test_a_successful_request_clears_the_breaker(monkeypatch):
    opener = use_opener(monkeypatch, FakeOpener(failures=1))
    client = make_client()
    client._request("/api/sync")

    assert client._down_until == 0.0
    assert client._down_reason == ""


def test_a_store_request_is_never_repeated(monkeypatch):
    """POST /api/ciphers creates an item - a retry could duplicate it."""
    opener = use_opener(monkeypatch, FakeOpener(failures=None))
    with pytest.raises(vault_store.VaultError):
        make_client()._request("/api/ciphers", method="POST", payload={"name": "X"})

    assert opener.calls == 1


def test_the_failure_message_never_carries_the_password(monkeypatch):
    use_opener(monkeypatch, FakeOpener(failures=None))
    client = make_client()
    with pytest.raises(vault_store.VaultError) as excinfo:
        client._request("/api/sync")

    assert PASSWORD not in str(excinfo.value)


def test_an_http_error_is_still_not_retried(monkeypatch):
    """A 404/500 is an answer, not a transport failure."""

    class AnsweringOpener:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout=None):
            self.calls += 1
            raise urllib.error.HTTPError(
                request.full_url, 500, "server error", email.message.Message(), None
            )

    opener = AnsweringOpener()
    monkeypatch.setattr(vault_store, "_SAFE_OPENER", opener)
    with pytest.raises(vault_store.VaultError) as excinfo:
        make_client()._request("/api/sync")

    assert opener.calls == 1
    assert "the vault answered 500" in str(excinfo.value)
