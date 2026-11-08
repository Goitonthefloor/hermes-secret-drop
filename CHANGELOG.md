# Changelog

## 2026-11-08 — 1.5.0

- Secrets are referenced as `{{secret:NAME}}`. A `pre_tool_call` hook substitutes the value in `terminal` and `execute_code` arguments in memory, so the value never enters the chat, the model context, or a provider request.
- The same hook refuses every `terminal` and `execute_code` call that names the store, glob spellings and mutating commands on the Hermes home included, so the store cannot be read, copied, moved or erased from a tool call.
- `transform_terminal_output` and `transform_tool_result` scrub stored values and their base64 (standard/URL-safe, padded/unpadded), hex, URL-encoded, reversed, and character-separated forms before tool output reaches the model.
- The session prompt, skill, all nine desktop locales, and the README state the real guarantee instead of claiming the model can never see a value.
- The drop route reads its body under a hard 32 KiB cap with `request.stream()` and answers 413 for oversized requests, including chunked bodies without `Content-Length`.
- `_public_error` no longer passes host exception text to HTTP or CLI callers; details are logged server-side with the value removed.
