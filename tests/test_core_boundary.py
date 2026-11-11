"""Core boundaries: no private core structures, no undeclared YAML dependency."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import secret_drop as drop
from secret_guard import REDACTED, scrub_text


@pytest.fixture
def home(tmp_path, monkeypatch):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    import secret_guard

    secret_guard._INJECTED.clear()
    return hermes


def test_config_credentials_are_scrubbed_without_pyyaml(home, monkeypatch):
    """PyYAML is not a Hermes dependency; core's parser is the one to use."""
    value = "cfg-Session-Value-77"
    (home / "config.yaml").write_text(
        "dashboard:\n  basic_auth:\n    secret: '%s'\n    username: 'admin'\n" % value,
        encoding="utf-8",
    )
    # Any import of PyYAML now fails the way it fails on a stock install.
    monkeypatch.setitem(sys.modules, "yaml", None)
    cleaned = scrub_text("token=%s done" % value)
    assert value not in cleaned and REDACTED in cleaned


class StrictPassthrough(types.ModuleType):
    """A core module that refuses the private names a plugin must not touch."""

    def __getattr__(self, name: str):
        if name in ("_allowed_env_vars", "_config_passthrough"):
            raise AssertionError("plugin touched a private core structure: " + name)
        raise AttributeError(name)


def test_revoking_passthrough_never_reaches_into_core(home, monkeypatch):
    """The config entry is dropped; the process-wide registry stays core's."""
    (home / "config.yaml").write_text(
        "terminal:\n  env_passthrough:\n    - OLD_DROP_NAME\n    - UNRELATED\n",
        encoding="utf-8",
    )
    fake = StrictPassthrough("tools.env_passthrough")
    package = types.ModuleType("tools")
    setattr(package, "env_passthrough", fake)
    monkeypatch.setitem(sys.modules, "tools", package)
    monkeypatch.setitem(sys.modules, "tools.env_passthrough", fake)

    removed = drop._revoke_passthrough({"OLD_DROP_NAME"})

    assert removed == ["OLD_DROP_NAME"]
    text = (home / "config.yaml").read_text(encoding="utf-8")
    assert "OLD_DROP_NAME" not in text
    assert "UNRELATED" in text
