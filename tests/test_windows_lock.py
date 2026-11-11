"""The index lock has a native Windows backend, and a host without one is refused."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import secret_drop as d


class FakeMsvcrt:
    """Stand-in for the Windows module: records the calls and can fail on purpose."""

    LK_NBLCK = "nblck"
    LK_UNLCK = "unlck"

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[tuple[str, int, int]] = []

    def locking(self, fd: int, mode: str, count: int) -> None:
        self.calls.append((mode, count, os.fstat(fd).st_size))
        if mode == self.LK_NBLCK and self.failures:
            self.failures -= 1
            raise OSError("locked by another process")


@pytest.fixture
def home(tmp_path, monkeypatch):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    return hermes


@pytest.fixture
def windows(monkeypatch):
    fake = FakeMsvcrt()
    monkeypatch.setattr(d, "fcntl", None)
    monkeypatch.setattr(d, "msvcrt", fake)
    monkeypatch.setattr(d, "_LOCK_RETRY_S", 0.0)
    return fake


def test_the_windows_backend_locks_and_unlocks_one_byte(home, windows):
    """An empty lock file is given the byte its range lock needs."""
    with d._index_lock():
        assert windows.calls == [("nblck", 1, 1)]
    assert windows.calls[-1][0] == "unlck"
    lock = home / d._INDEX_LOCK_FILE
    assert lock.exists() and lock.stat().st_size == 1
    assert lock.stat().st_mode & 0o777 == 0o600


def test_the_windows_backend_retries_a_held_lock(home, monkeypatch):
    fake = FakeMsvcrt(failures=2)
    monkeypatch.setattr(d, "fcntl", None)
    monkeypatch.setattr(d, "msvcrt", fake)
    monkeypatch.setattr(d, "_LOCK_RETRY_S", 0.0)
    with d._index_lock():
        pass
    assert [call[0] for call in fake.calls] == ["nblck", "nblck", "nblck", "unlck"]


def test_a_lock_that_never_arrives_raises_instead_of_writing(home, monkeypatch):
    """Fail closed: the caller never runs its read-modify-write unlocked."""
    fake = FakeMsvcrt(failures=10_000)
    monkeypatch.setattr(d, "fcntl", None)
    monkeypatch.setattr(d, "msvcrt", fake)
    monkeypatch.setattr(d, "_LOCK_TIMEOUT_S", 0.05)
    monkeypatch.setattr(d, "_LOCK_RETRY_S", 0.01)
    entered = False
    with pytest.raises(TimeoutError):
        with d._index_lock():
            entered = True
    assert entered is False


def test_a_host_without_a_lock_backend_is_refused(home, monkeypatch):
    monkeypatch.setattr(d, "fcntl", None)
    monkeypatch.setattr(d, "msvcrt", None)
    with pytest.raises(RuntimeError):
        with d._index_lock():
            pass


def test_stores_keep_every_name_on_the_windows_backend(home, windows):
    """Every writer's name survives when the Windows branch does the locking."""
    for index in range(6):
        d._remember_name("NAME_%d" % index)
    assert sorted(d.stored_secret_names()) == ["NAME_%d" % index for index in range(6)]
