# Changelog

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
