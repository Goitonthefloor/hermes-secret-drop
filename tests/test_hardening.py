"""Hardening regressions: wildcard spellings, unknown tools, aliases, index, mode, needles."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from secret_drop import accept_secret_file, stored_secret_names
from secret_guard import REDACTED, guard_store_access, guarded_paths, scrub_text

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


def _guarded() -> list[str]:
    """Names of the guarded files, taken from the module so no test spells them."""
    return [item.name for item in guarded_paths()]


def test_a_wildcard_spelling_of_the_store_is_blocked(stored):
    """A glob names the store without spelling it, so a literal match cannot see it."""
    listing, index, drop_dir = _guarded()
    here = str(stored)
    for command in (
        "cat %s/.e*" % here,
        "cat %s/*%s" % (here, listing[1:]),
        "head %s/%s*" % (here, index[:7]),
        "grep -r x %s/%s" % (here, drop_dir.replace("s", "*", 1)),
    ):
        assert guard_store_access("terminal", {"command": command}), command
    # Ordinary wildcards and ordinary directories stay usable.
    assert guard_store_access("terminal", {"command": "ls -la %s/*" % here}) is None
    assert guard_store_access("terminal", {"command": "grep -rn drop src/*"}) is None


def test_a_tool_outside_the_name_table_cannot_reach_the_store(stored):
    """An unknown tool name must not be treated as harmless when it names the store."""
    listing = _guarded()
    target = str(stored / listing[1])
    assert guard_store_access("browser_exec", {"code": "open(%r).read()" % target})
    assert guard_store_access("some_future_tool", {"arguments": {"file": target}})
    assert guard_store_access("honcho_search", {"query": "quarterly numbers"}) is None


def test_a_payload_path_is_resolved_and_not_only_matched(stored, tmp_path):
    """An alias such as a symlink carries no store name, so it has to be resolved."""
    alias = tmp_path / "notes.txt"
    alias.symlink_to(stored / _guarded()[0])
    payload = "*** Begin Patch\n*** Delete File: %s\n*** End Patch\n" % alias
    assert guard_store_access("patch", {"mode": "patch", "patch": payload})


def test_the_plugin_checkout_stays_readable_and_patchable(stored):
    """The plugin's own folder name is not a store spelling."""
    guard = ROOT / "secret_guard.py"
    assert guard_store_access("read_file", {"path": str(guard)}) is None
    assert guard_store_access("patch", {"path": str(guard), "old_string": "a", "new_string": "b"}) is None


def test_a_wider_env_mode_is_narrowed_when_storing(home):
    """The owner-only promise is enforced here, not inherited from the core writer."""
    target = home / _guarded()[0]
    target.write_text("EXISTING=1\n", encoding="utf-8")
    fd = os.open(str(target), os.O_WRONLY)
    try:
        os.fchmod(fd, 0o644)
    finally:
        os.close(fd)
    accept_secret_file("DEPLOY_PASSWORD", SECRET)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_a_credential_in_the_config_file_becomes_a_needle(home):
    """A config credential is in neither the store nor the environment."""
    value = "cfg-Session-Value-77"
    (home / "config.yaml").write_text(
        "dashboard:\n  basic_auth:\n    secret: '%s'\n    username: 'admin'\n" % value,
        encoding="utf-8",
    )
    cleaned = scrub_text("token=%s done" % value)
    assert value not in cleaned and REDACTED in cleaned


def test_concurrent_stores_keep_every_name(home):
    """Two writers lost one name because the lock was process-local."""
    code = (
        "import sys; sys.path.insert(0, %r); import secret_drop as d; d._remember_name(sys.argv[1])"
        % str(ROOT)
    )
    child_env = dict(os.environ, HERMES_HOME=str(home))
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", code, "NAME_%d" % index], env=child_env, close_fds=True
        )
        for index in range(6)
    ]
    for proc in procs:
        assert proc.wait(timeout=120) == 0
    assert sorted(stored_secret_names()) == ["NAME_%d" % index for index in range(6)]


def test_no_locale_claims_the_value_cannot_reach_the_model():
    """The dialog may promise the chat, not the model context."""
    js = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
    for phrase in (
        "model context",
        "never sees",
        "Modellkontext",
        "模型上下文",
        "モデルのコンテキスト",
        "سياق النموذج",
        "контекст модели",
        "contexte du modèle",
        "contexto del modelo",
    ):
        assert phrase not in js, phrase
    assert js.count("description:") >= 9
    assert js.count("valueIsolated:") >= 9
