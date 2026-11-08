---
name: secret-drop
description: Use stored secrets through the {{secret:NAME}} alias; never ask the user to paste a value into the chat.
---

# Secret drop

When a task needs a password, token, or other secret:

- Do not ask the user to paste the value into the chat, a tool argument, or a file you can read.
- Tell them to open Hermes Desktop and use the key button beside the composer, or run `/secret` and type the value in the masked field.
- Use the secret only as `{{secret:NAME}}` inside a `terminal` command or an `execute_code` body, for example:

  ```text
  curl -H "Authorization: Bearer {{secret:DEPLOY_TOKEN}}" https://api.example.test
  ```

  The gateway replaces the alias with the stored value in the arguments it executes. The value is not written back into the conversation, so it stays out of the model context.
- Never print, copy, log, decode, or otherwise reveal the value. Do not ask the user for it and do not try to read the store: `read_file`, `search_files`, `terminal`, and `execute_code` are blocked on `.env`, `secret-drop-names`, and `secret-drops/`, and tool output scrubs known values and encodings.
- An unknown alias, an empty value, or a provider credential such as `OPENAI_API_KEY` blocks the call. Ask the user to store the secret again; do not work around the block.
- Sandboxed commands receive a stored value only through the alias path that the gateway approves; provider credentials are never injected.
