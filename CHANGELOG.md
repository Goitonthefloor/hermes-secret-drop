# Changelog

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
