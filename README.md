# secret-drop

Give Hermes a password or token without putting it in the chat or showing it to the model.

This is a standalone Hermes plugin. It is not part of the Hermes core tree. The agent half installs into the gateway's `plugins/` directory. The desktop half installs into this app's `desktop-plugins/` directory. That split is the distribution path described in [CONTRIBUTING.md](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md) and [Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).

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

The desktop half is the repository root. The gateway half is the `plugin/` directory. Hermes treats a repository that contains both `plugin.yaml` and `desktop/plugin.js` as one package, copies the desktop half out, and deletes that copy on the next scan when the package is not on this machine. A remote gateway is that case, so **Install from Git** of a combined package leaves the Plugins row on **unavailable (remote backend)**. Installing the desktop half on its own writes no package marker, and the copy stays.

```
hermes-secret-drop/
├── desktop/
│   └── plugin.js               # composer key, palette command, masked dialog
└── plugin/
    ├── plugin.yaml
    ├── __init__.py             # /secret, session-start redaction reload, session prompt
    ├── secret_drop.py          # file drop, .env store, wipe
    ├── skills/secret-drop/SKILL.md
    └── dashboard/
        ├── manifest.json
        └── plugin_api.py       # POST /api/plugins/secret-drop/drop
```

The desktop half turns on when it is installed (`defaultEnabled: true`). The agent half follows `plugins.enabled` and needs a gateway restart so the route is mounted.

## Install

In Hermes Desktop, **Capabilities → Plugins → Install from Git**.

Desktop UI, on the machine running Hermes Desktop:

```text
Goitonthefloor/hermes-secret-drop
```

```text
hermes://plugin/install?repo=Goitonthefloor/hermes-secret-drop
```

The dialog offers **Desktop UI** only. After it finishes, the key sits in the composer, to the left of the model pill. **Rescan** if the row is missing. A hand-copied `~/.hermes/desktop-plugins/secret-drop/` from an earlier attempt uses the same plugin id; remove that folder first so the two copies do not conflict.

Agent half, on the gateway the app is connected to (local or remote):

```text
Goitonthefloor/hermes-secret-drop/plugin
```

```bash
hermes plugins install Goitonthefloor/hermes-secret-drop/plugin
hermes plugins enable secret-drop
```

Or copy `plugin/` to `~/.hermes/plugins/secret-drop` on that host and enable it the same way. Restart the gateway afterwards.

A gateway package installed from the repository root of an older commit still contains `desktop/plugin.js`. Hermes then keeps showing **unavailable (remote backend)** on that row. Install `Goitonthefloor/hermes-secret-drop/plugin` again with **Force reinstall** so that package no longer advertises a desktop half. The key comes from the Desktop UI row, named **Secret drop**.

A catalog entry is a separate reviewed pull request in `NousResearch/hermes-agent` `plugin-catalog/`, pinned to an exact commit of this repo. Do not add this plugin to the Hermes core tree.

## Tests

From this directory, with the Hermes checkout importable:

```bash
PYTHONPATH=/path/to/hermes-agent python -m pytest tests/test_drop.py
```
