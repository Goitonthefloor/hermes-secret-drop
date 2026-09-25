# secret-drop

Give Hermes a password or token without putting it in the chat or showing it to the model.

This is a standalone Hermes plugin. It is not part of the Hermes core tree. Install it into `~/.hermes/plugins/` and enable it. That is the distribution path described in [CONTRIBUTING.md](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md) and [Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).

## What it does

Hermes Desktop shows a key button beside the composer and a command-palette entry, **Give Hermes a secret**. The masked field sends the value once, over the gateway connection you already use (local backend, remote gateway, or SSH tunnel), to this plugin's API at `/api/plugins/secret-drop/drop`.

On that gateway host the plugin:

1. opens a new owner-only file under `secret-drops/`,
2. writes the secret and reads it back,
3. saves it in the profile `.env` (mode `0600`) under the name you chose,
4. deletes the file.

The response does not contain the value. Nothing is written into the transcript unless you leave **Tell Hermes the variable name** checked. That message names the variable only, for example `$DEPLOY_PASSWORD`.

Custom names are added to `terminal.env_passthrough`, so later sandboxed commands can expand `$NAME`. Provider and platform credentials such as `OPENAI_API_KEY` or `GITHUB_TOKEN` are stored but not forwarded. If a command prints the raw value, tool output replaces it with `«redacted-vault-secret»`. A command that encodes the value first is not covered by that exact-match redaction.

`/secret` in a local terminal asks for the name, then reads the value from a hidden prompt. On Telegram, Discord, and the other messaging platforms, `/secret` stores nothing and does not repeat the argument. Chat is the wrong place for a password.

## Layout

```
secret-drop/
├── plugin.yaml                 # agent half
├── __init__.py                 # /secret and the session-start redaction reload
├── secret_drop.py              # file drop, .env store, wipe
├── skills/secret-drop/SKILL.md
├── dashboard/
│   ├── manifest.json
│   └── plugin_api.py           # POST /api/plugins/secret-drop/drop
└── desktop/
    └── plugin.js               # composer button, palette command, masked dialog
```

Both halves stay off until you enable them. The Python half follows `plugins.enabled`. The desktop half is opt-in in **Capabilities → Plugins** (`defaultEnabled: false`).

Against a remote backend, install the agent half on the gateway host and the desktop half on the machine running Hermes Desktop. The desktop copy is local; the file is created on the host that serves `/api/plugins/secret-drop/`.

## Install

From a git remote, once this repository is published:

```bash
hermes plugins install owner/hermes-secret-drop
hermes plugins enable secret-drop
```

Or copy this directory to `~/.hermes/plugins/secret-drop` and enable it the same way. Then, in Hermes Desktop, turn on **Secret drop** under **Capabilities → Plugins** (or run **Rescan** if the desktop half does not appear).

Desktop install link, after the repo exists:

```text
hermes://plugin/install?repo=owner/hermes-secret-drop
```

A catalog entry is a separate reviewed pull request in `NousResearch/hermes-agent` `plugin-catalog/`, pinned to an exact commit of this repo. Do not add this plugin to the Hermes core tree.

## Tests

From this directory, with the Hermes checkout importable:

```bash
PYTHONPATH=/path/to/hermes-agent python -m pytest tests/test_drop.py
```
