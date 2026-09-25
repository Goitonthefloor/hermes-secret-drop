import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
import {
  Button,
  Checkbox,
  Codicon,
  COMPOSER_AREAS,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  host,
  Input,
  PALETTE_AREA,
  atom,
  useValue
} from '@hermes/plugin-sdk'

const $open = atom(false)
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/

function openDialog() {
  $open.set(true)
}

function SecretDropDialog({ rest }) {
  const open = useValue($open)
  const sessionId = useValue(host.state.focusedSessionId)
  const [name, setName] = useState('')
  const [value, setValue] = useState('')
  const [tell, setTell] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      setValue('')
      setSubmitting(false)
    }
  }, [open])

  if (!open) {
    return null
  }

  const submit = async event => {
    event.preventDefault()
    const secretName = name.trim()

    if (!NAME_RE.test(secretName)) {
      host.notify({ kind: 'warning', message: 'Use a variable name like DEPLOY_PASSWORD.' })

      return
    }

    if (!value) {
      return
    }

    const secret = value

    setValue('')
    setSubmitting(true)

    try {
      const result = await rest('/drop', {
        method: 'POST',
        body: { name: secretName, value: secret }
      })
      const stored = result.stored_as || secretName

      $open.set(false)
      host.notify({
        kind: 'success',
        message: result.passthrough
          ? `Stored as ${stored}. The model was not shown the value.`
          : `Stored as ${stored}. It is not forwarded into sandboxed commands.`
      })

      if (tell && sessionId) {
        const note = result.passthrough
          ? `I stored a secret in the environment variable ${stored}. Use $${stored} in commands. Do not ask me to paste the value, and do not print it.`
          : `I stored a credential in the environment variable ${stored}. Do not ask me to paste the value, and do not print it.`
        const sent = host.composer.submit(sessionId, note)

        if (!sent) {
          host.notify({
            kind: 'warning',
            message: 'The secret is stored, but Hermes was not told the variable name.'
          })
        }
      }
    } catch {
      host.notify({ kind: 'error', message: 'Could not store the secret' })
      setSubmitting(false)
    }
  }

  return jsx(Dialog, {
    open: true,
    onOpenChange: next => {
      if (!next && !submitting) {
        $open.set(false)
      }
    },
    children: jsx(DialogContent, {
      showCloseButton: false,
      children: jsxs('form', {
        className: 'grid gap-3',
        onSubmit: event => {
          void submit(event)
        },
        children: [
          jsxs(DialogHeader, {
            children: [
              jsx(DialogTitle, { children: 'Give Hermes a secret' }),
              jsx(DialogDescription, {
                children:
                  'The value is written to a file on the gateway host, saved as an environment variable, and the file is deleted. It is not added to the chat, and the model never sees it.'
              })
            ]
          }),
          jsxs('label', {
            className: 'grid gap-1 text-xs',
            children: [
              'Variable name',
              jsx(Input, {
                autoComplete: 'off',
                autoFocus: true,
                disabled: submitting,
                onChange: event => setName(event.target.value),
                placeholder: 'DEPLOY_PASSWORD',
                spellCheck: false,
                value: name
              })
            ]
          }),
          jsxs('label', {
            className: 'grid gap-1 text-xs',
            children: [
              'Secret',
              jsx(Input, {
                autoComplete: 'new-password',
                disabled: submitting,
                onChange: event => setValue(event.target.value),
                placeholder: 'Hidden',
                spellCheck: false,
                type: 'password',
                value: value
              })
            ]
          }),
          jsx('p', {
            className: 'text-xs text-muted-foreground',
            children:
              'Later commands can use $NAME. Printed values are redacted in tool output. Provider credentials stay out of sandboxed commands.'
          }),
          jsxs('label', {
            className: 'flex items-center gap-2 text-xs text-muted-foreground',
            children: [
              jsx(Checkbox, {
                checked: tell,
                disabled: submitting || !sessionId,
                onCheckedChange: checked => setTell(checked === true)
              }),
              'Tell Hermes the variable name'
            ]
          }),
          jsxs(DialogFooter, {
            children: [
              jsx(Button, {
                disabled: submitting,
                onClick: () => $open.set(false),
                type: 'button',
                variant: 'ghost',
                children: 'Cancel'
              }),
              jsx(Button, {
                disabled: submitting || !value || !name.trim(),
                type: 'submit',
                children: submitting ? 'Storing…' : 'Store secret'
              })
            ]
          })
        ]
      })
    })
  })
}

function SecretDropButton({ rest }) {
  return jsxs('span', {
    className: 'inline-flex',
    children: [
      jsx(Button, {
        'aria-label': 'Give Hermes a secret',
        onClick: () => openDialog(),
        size: 'icon',
        type: 'button',
        variant: 'ghost',
        children: jsx(Codicon, { name: 'key' })
      }),
      jsx(SecretDropDialog, { rest })
    ]
  })
}

export default {
  id: 'secret-drop',
  name: 'Secret drop',
  defaultEnabled: false,
  register(ctx) {
    const rest = (path, opts) => ctx.rest(path, opts)

    ctx.register({
      id: 'composer',
      area: COMPOSER_AREAS.actions,
      render: () => jsx(SecretDropButton, { rest })
    })
    ctx.register({
      id: 'palette',
      area: PALETTE_AREA,
      data: {
        id: 'secret-drop.open',
        label: 'Give Hermes a secret',
        keywords: ['password', 'token', 'secret', 'env'],
        run: () => openDialog()
      }
    })
  }
}
