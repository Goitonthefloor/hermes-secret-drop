# Changelog

## 2026-11-13 — 1.7.0

- **Configuration lives in the plugins hub.** The manifest now declares a `config_schema` (backend choice, vault URL, and the two login values as `secret` fields), so the Desktop/TUI plugins hub renders a form and writes `plugins.entries.secret-drop.settings`; the client reads that block and resolves the credentials through `agent.secret_scope.get_secret()` with the profile environment file as the second source. No secrets in `config.yaml`, no hand-edited YAML.
- Optional Vaultwarden backend. `settings.backend: vaultwarden` stores a new secret as a login item in a Bitwarden-compatible vault and resolves `{{secret:NAME}}` from there; the default stays the profile environment file, and a name that is not in the vault still falls back to that file, so nothing has to be migrated before switching. A configured but unreachable vault blocks the alias instead of serving another store.
- `vault_store.py` is a native client: token login with the client-derived `masterPasswordHash`, keys via HKDF-Expand over the master key, AES-CBC-HMAC item encryption, per-item keys unwrapped when an item carries one. No `bw`/`rbw` process per lookup - the alias hook runs on every tool call.
- Two API details cost a diagnosis each and are now documented: `POST /api/ciphers` rejects a payload without `encryptedFor` with a bare HTTP 422, and the token endpoint answers "Username or password is incorrect" for a plaintext master password.
- Twelve tests: the configuration gate (an incomplete vault section falls back to the file store), storing into the vault without touching the environment file, the username as `<NAME>_USER`, the unreachable-vault block, needless fallback of an indexed name, needles from the vault, and the encrypt/decrypt round trip including a tampered MAC. The suite is 89 tests.

## 2026-11-11 — 1.6.5

- The plugin no longer reaches into core. `_revoke_passthrough()` used to `discard()` from `tools.env_passthrough._allowed_env_vars` and to clear `_config_passthrough` — private, process-wide structures a plugin must not change, because it breaks other plugins now and any future core release. It still drops the name from the profile config (the user's own file) and still calls `unregister_env_passthrough` when the core grows one; until then it logs what it dropped and the README names the one upgrade step: restart the gateway once after upgrading from a version before 1.5.1, since a registration an older version made lives only in core memory.
- The profile-config scrubbing works on a stock install. `_config_credential_values()` imported PyYAML, which is not a Hermes dependency, and a bare `except` turned that ImportError into an empty needle set: credential values kept in the profile config were never scrubbed on a machine without PyYAML. It now reads the config through core's public `hermes_cli.config.load_config_readonly()` — no private import, no undeclared dependency — and logs when the file cannot be read instead of failing silently.
- Two regression tests: one makes `import yaml` fail the way a stock install does and still expects the config value to be redacted, one hands the plugin a stand-in core module that raises on any access to `_allowed_env_vars` or `_config_passthrough`. Both fail on 1.6.4 and pass now. The suite is 80 tests.

## 2026-11-11 — 1.6.4

- The README says when the composer key is missing, and why. A desktop half that carries a `hermes-package.json` marker ships opt-in: the desktop loader caps its own `defaultEnabled` and skips the plugin until the switch under **Capabilities → Plugins** is on. The agent half reports enabled while the composer stays empty, because the two halves have separate rows and separate switches, and `hermes plugins install` does not flip the desktop one.
- The Install section states that the switch is not optional after a command-line install, and the layout section names the marker as the reason. Turned on once per desktop installation; the choice is remembered.

## 2026-11-11 — 1.6.3

- The index lock covers native Windows. `msvcrt.locking` takes an exclusive byte-range lock on the same owner-only lock file that `flock` covers on POSIX, so two gateway processes on a Windows host no longer keep only one of the two new names in the index. On Windows the lock file is opened readable, a zero-length file gets the one byte the range needs first, and the wait is retried in short steps because `msvcrt` gives up after ten one-second attempts.
- A lock that does not arrive within 30 seconds raises instead of letting the caller write the index unlocked, and a host with neither backend is refused rather than unserialised. Both paths fail closed: a name missing from the index is a stored value that stops being a redaction needle after a restart.
- Five tests drive the Windows branch explicitly, since native Windows is not a CI target: one byte locked and unlocked, a held lock retried, a timeout that raises before the caller runs, a missing backend, and six stores keeping every name. The suite is 78 tests.

## 2026-11-10 — 1.6.2

- Wildcard spellings of the store are refused: a leading-dot wildcard, a wildcard in place of the index prefix or inside the file name is compared with the guarded file names, so `~/.hermes/.e*` no longer walks past the guard. A plain `*` and ordinary directory globs still run.
- A tool outside the screened names is swept instead of trusted. Every string argument of any tool is checked for a store name or for a path that resolves into the store, so a new tool cannot silently widen the read surface while unrelated calls stay untouched.
- Paths inside a write payload are resolved, not only matched: a symlink alias that points at a guarded file is caught by the same rule that covers an explicit path argument.
- The plugin's own folder name is no longer treated as a store spelling. Resolving a path decides first and the text fallback only covers unresolvable spellings, so `read_file` and `patch` work on the plugin source again.
- The index read-modify-write is serialised across processes with `flock`. The thread lock could not see a CLI store writing the same profile, and two overlapping stores kept only one of the two new names.
- Storing narrows the profile env file to mode `0600` itself instead of inheriting whatever mode the core writer left, and fails closed when the mode cannot be established.
- Credential values in the profile config file become scrubber needles. They are in neither the store nor the environment, so a dashboard session secret printed by a tool call reached the model unredacted.
- The Desktop dialog, its nine locale bundles and the manifest description no longer promise a model-context guarantee. They now say what holds (the value is not added to the chat) and what depends on the rules (a specific-enough value is scrubbed from tool output). The README repeats the same limit at the top of its security model.
- The write-tool guard walks every string in the call arguments, nested dicts and lists and their keys included, instead of only the top-level strings. A write tool that keeps its edits in a nested list (`edits: [{"patch": ...}]`) or in a mapping keyed by file path could name the guarded store and pass uninspected, which is the same hole the V4A headers once were. `_guard_write` now inspects the whole argument tree; benign replace-mode and V4A patches still run.
- Regression tests cover a nested delete payload, a nested edit whose content names a file inside the `secret-drops/` directory, a change set keyed by the store path, and a nested edit that touches no store file (which must still run).
- The directory arguments of a command tool are inspected too. `terminal` carries a `workdir` next to the command, so `rm -f .env` with `workdir` set to the profile home was a store write that no text rule could see; a `cd` into the home persists the same state across calls. Both are refused now, by resolved path, while a project or plugin checkout inside the home stays usable. The suite is 73 tests.

## 2026-11-10 — 1.6.1

- A secret stored directly under a `*_USER` name keeps its output scrubbing. The suffix alone no longer marks a name as an account name: `is_account_name()` now consults the account index this plugin writes when it stores a generated username. `accept_secret_file("DEPLOY_USER", "s3cret-value-9001")` therefore registers a needle like any other secret instead of being skipped by `persisted_secret_values()`, by `load_secret_values()` and by the empty-store fail-closed check.
- Storing a secret under a name that already held a generated username removes that name from the account index first, so the value counts as a credential from then on.
- The account index (`account-index` beside the profile home) is part of the guarded store: `read_file`, `search_files`, `write_file`/`patch` and terminal or `execute_code` text cannot read, empty or extend it, so a model cannot switch a stored secret out of the scrubber by editing the index.
- Four regression tests cover the reported shape (`DEPLOY_USER` with a credential-shaped value), the account-name classification, the overwrite case and the guard on the index. The suite is 63 tests.
- Documentation: the username paragraph in the README states that only a name this plugin wrote counts as an account name.

## 2026-11-09 — 1.6.0

- The drop dialog has an optional **Username** field. When it is filled, the name is stored next to the secret as `<NAME>_USER`, so a login can be used as `{{secret:NAME_USER}}` instead of being invented by the model. The field is skipped when it is empty or blank.
- A username is an account name, not a credential: it is injectable through an alias, but it is never registered as a global output needle, so ordinary mentions of the account are not rewritten.
- The optional field travels as `username` in the drop request body. A non-string value is a 400, an invalid one (line break, non-ASCII, longer than 256 characters) is refused before anything is stored, and a failure to store the username does not fail the secret that was stored with it.
- README, changelog, the CLI reply and the desktop message name `<NAME>_USER` when it was stored.

## 2026-11-09 — 1.5.1

- Storing a secret no longer adds its name to `terminal.env_passthrough`. That entry made `$NAME` expand inside a tool command, so a command that printed its environment returned the value to the model even though the alias never touched it. A name that an earlier version added is removed on the next store and once per session start.
- `pre_tool_call` now covers the environment path: a command or `execute_code` body that names a stored variable (`$NAME`, `${NAME}`, `printenv NAME`, `os.environ[...]`, `getenv(...)`) registers that value as a needle for the single call, so a short or word-like value is scrubbed from its output as well. A bare environment dump (`env`, `printenv`, `set`, `export -p`, `/proc/self/environ`, `os.environ` as a whole) is refused while stored names exist.
- The store response reports `injectable` instead of `passthrough`: the flag now means "usable through the alias", which is what the desktop already displayed.
- Seven regression tests cover the reported bypass (`printf '%s' "$DEPLOY_PASSWORD"` with a word-like value), the Python spelling, the dump refusal, the over-blocking counter-check, and both passthrough clean-up paths.

## 2026-11-08 — 1.5.0

- Secrets are referenced as `{{secret:NAME}}`. A `pre_tool_call` hook substitutes the value in `terminal` and `execute_code` arguments in memory, so the value never enters the chat, the model context, or a provider request.
- The same hook refuses a tool call that names the store — glob spellings, `write_file`/`patch` targets and mutating commands on the Hermes home included. What the guard does not recognise is covered by output scrubbing, not by the guard.
- `transform_terminal_output` and `transform_tool_result` scrub stored values and their base64 (standard/URL-safe, padded/unpadded), hex, URL-encoded, reversed, and character-separated forms before tool output reaches the model.
- The session prompt, skill, all nine desktop locales, and the README state the real guarantee instead of claiming the model can never see a value.
- The drop route reads its body under a hard 32 KiB cap with `request.stream()` and answers 413 for oversized requests, including chunked bodies without `Content-Length`.
- `_public_error` no longer passes host exception text to HTTP or CLI callers; details are logged server-side with the value removed.
