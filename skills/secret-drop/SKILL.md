---
name: secret-drop
description: Ask the user to enter a secret in the Hermes Desktop secure field. Never ask them to paste the value into the chat.
---

# Secret drop

When a task needs a password, token, or other secret:

- Do not ask the user to paste the value into the chat, a tool argument, or a file you can read.
- Tell them to open Hermes Desktop and use the key button beside the composer, or run `/secret` and type the value in the masked field.
- You may use the environment variable name they give you, for example `$DEPLOY_PASSWORD`.
- Do not print, log, or encode that variable. Tool output redacts a credential-shaped value (at least 8 characters with a digit or symbol, or at least 24 characters). A short or plain-word value is stored but not used as a global search-and-replace. Encoding a redacted value on purpose defeats that.
- Provider credentials such as `OPENAI_API_KEY` are stored, but sandboxed commands do not receive them.
