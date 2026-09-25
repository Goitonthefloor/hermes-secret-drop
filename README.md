# secret-drop

Give Hermes a password or token without putting it in the chat or showing it to the model.

This is a standalone Hermes plugin. It is not part of the Hermes core tree. Install the repository root into `~/.hermes/plugins/`. That is the distribution path described in [CONTRIBUTING.md](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md) and [Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).

## What it does

Hermes Desktop shows a key button beside the composer and a command-palette entry, **Give Hermes a secret**. The masked field sends the value once, over the gateway connection you already use (local backend, remote gateway, or SSH tunnel), to this plugin's API at `/api/plugins/secret-drop/drop`.

On that gateway host the plugin:

1. opens a new owner-only file under `secret-drops/`,
2. writes the secret and reads those same bytes back,
3. saves them in the profile `.env` (mode `0600`) under the name you chose, and checks the read-back,
4. deletes the file.

The response does not contain the value. Nothing is written into the transcript unless you leave **Tell Hermes the variable name** checked. That message names the variable only, for example `$DEPLOY_PASSWORD`. If storing succeeds and the follow-up message fails, the dialog says the secret is stored.

When the dashboard is serving more than one profile, the desktop `profile` query selects which profile receives the value. A request for another profile does not write the launch profile's `.env`.

Custom names are added to the raw `terminal.env_passthrough` list, so later sandboxed commands can expand `$NAME`. That write does not save the defaults-merged config, so `${...}` templates already in `config.yaml` stay templates. Provider and platform credentials such as `OPENAI_API_KEY` or `GITHUB_TOKEN` are stored but not forwarded.

If a command prints the raw value, tool output replaces it with `«redacted-vault-secret»` only when the value is specific enough to redact: at least 8 characters and containing a digit or symbol, or at least 24 characters. A short value or a plain word such as `password` is stored, and is not used as a global search-and-replace. Hermes keeps at most 64 of these exact values in memory per profile; this plugin records the variable names in `secret-drop-names` and registers the values again on session start. A command that encodes the value first is not covered by that exact-match redaction.

The same guidance is added to the session prompt when Hermes supports plugin prompt sections. The bundled skill `secret-drop:secret-drop` is listed by `skills_list` and is not copied into `~/.hermes/skills/`.

`/secret` in a local terminal asks for the name, then reads the value from a hidden prompt. On Telegram, Discord, and the other messaging platforms, `/secret` stores nothing and does not repeat the argument. Chat is the wrong place for a password.

## Limits

The value must be non-empty ASCII, at most 8192 characters, and must not contain a line break or a NUL. Names have to be normal environment variable names. Hermes refuses names that steer a subprocess (`PATH`, `LD_PRELOAD`, `PYTHONPATH`, and the rest of that denylist).

## Layout

`plugin.yaml` sits at the repository root. Hermes then records the allow-list entry as the manifest name `secret-drop`. That is the same string as the dashboard manifest and the desktop plugin id, and it is the path segment in `POST /api/plugins/secret-drop/drop`.

A `plugin.yaml` nested in a subdirectory is recorded as a path key (`hermes-secret-drop/hermes-secret-drop/plugin`). The dashboard gate compares the request path to `plugins.enabled` and does not accept that path key, so the call returns 404 `Plugin not found`.

```
hermes-secret-drop/
├── plugin.yaml                 # name: secret-drop
├── __init__.py                 # /secret, session-start redaction reload, session prompt
├── secret_drop.py              # file drop, .env store, wipe
├── skills/secret-drop/SKILL.md
├── dashboard/
│   ├── manifest.json           # name: secret-drop
│   └── plugin_api.py           # POST /api/plugins/secret-drop/drop
└── desktop/
    └── plugin.js               # id: secret-drop
```

The agent half follows `plugins.enabled` and needs a gateway restart so the route is mounted. The desktop half stays off until its own switch is on.

## Install

Install the repository root, not a subdirectory.

```bash
hermes plugins install Goitonthefloor/hermes-secret-drop
hermes plugins enable secret-drop
```

```text
hermes://plugin/install?repo=Goitonthefloor/hermes-secret-drop
```

`plugins.enabled` must contain `secret-drop`. Remove a path key such as `hermes-secret-drop/hermes-secret-drop/plugin`, and delete a leftover checkout under `~/.hermes/plugins/hermes-secret-drop/` that still has `plugin/plugin.yaml` inside it. Restart the gateway after enabling.

In Hermes Desktop, turn on **Secret drop** under **Capabilities → Plugins**. The key sits in the composer, to the left of the model pill.

A catalog entry is a separate reviewed pull request in `NousResearch/hermes-agent` `plugin-catalog/`, pinned to an exact commit of this repo. Do not add this plugin to the Hermes core tree.

## Tests

From this directory, with the Hermes checkout importable:

```bash
PYTHONPATH=/path/to/hermes-agent python -m pytest tests/test_drop.py
```
