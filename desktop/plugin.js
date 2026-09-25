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
const HOST_EVENT = 'secret-drop-dialog-host'
let dialogHost = 0
let nextDialogHost = 0

function openDialog() {
  $open.set(true)
}

function failureMessage(error, secret) {
  const message = error && typeof error.message === 'string' ? error.message.trim() : ''

  if (!message || message.length > 300 || (secret && message.includes(secret))) {
    return 'Could not store the secret'
  }

  return message
}

function successMessage(stored, result) {
  const parts = [`Stored as ${stored}.`, 'The model was not shown the value.']

  if (result && result.passthrough === false) {
    parts.push('It is not forwarded into sandboxed commands.')
  }

  if (result && result.redacted === false) {
    parts.push('Tool output will not redact this value.')
  }

  if (result && result.indexed === false) {
    parts.push('A later session may not redact it.')
  }

  return parts.join(' ')
}

function modelNote(stored, result) {
  const passthrough = !result || result.passthrough !== false
  const redacted = !result || result.redacted !== false
  const use = passthrough
    ? `Use $${stored} in commands.`
    : 'Sandboxed commands do not receive it.'
  const redact = redacted
    ? 'Do not ask me to paste the value, and do not print it.'
    : 'Do not ask me to paste the value, print it, or encode it. Tool output will not redact it.'

  return `I stored a secret in the environment variable ${stored}. ${use} ${redact}`
}

function useDialogHost() {
  const id = useState(() => {
    nextDialogHost += 1

    return nextDialogHost
  })[0]
  const [active, setActive] = useState(false)

  useEffect(() => {
    let cancelled = false

    const claim = () => {
      if (cancelled || (dialogHost !== 0 && dialogHost !== id)) {
        return
      }

      dialogHost = id
      setActive(true)
    }

    claim()

    const target = typeof window === 'undefined' ? null : window

    target?.addEventListener(HOST_EVENT, claim)

    return () => {
      cancelled = true
      setActive(false)
      target?.removeEventListener(HOST_EVENT, claim)

      if (dialogHost === id) {
        dialogHost = 0
        target?.dispatchEvent(new Event(HOST_EVENT))
      }
    }
  }, [id])

  return active
}

function SecretDropDialog({ rest }) {
  const open = useValue($open)
  const sessionId = useValue(host.state.focusedSessionId)
  const [name, setName] = useState('')
  const [value, setValue] = useState('')
  const [tell, setTell] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) {
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

    setSubmitting(true)

    let result

    try {
      result = await rest('/drop', {
        method: 'POST',
        body: { name: secretName, value: secret }
      })
    } catch (error) {
      host.notify({ kind: 'error', message: failureMessage(error, secret) })
      setSubmitting(false)

      return
    }

    setValue('')
    setSubmitting(false)
    $open.set(false)

    const stored = (result && result.stored_as) || secretName

    host.notify({ kind: 'success', message: successMessage(stored, result) })

    let session = sessionId

    try {
      session = host.state.focusedSessionId.get()
    } catch {
      session = sessionId
    }

    if (!tell) {
      return
    }

    if (!session) {
      host.notify({
        kind: 'warning',
        message: 'The secret is stored, but there is no open chat to tell the variable name.'
      })

      return
    }

    try {
      const sent = host.composer.submit(session, modelNote(stored, result))

      if (!sent) {
        host.notify({
          kind: 'warning',
          message: 'The secret is stored, but Hermes was not told the variable name.'
        })
      }
    } catch {
      host.notify({
        kind: 'warning',
        message: 'The secret is stored, but Hermes was not told the variable name.'
      })
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
              'Later commands can use $NAME. Printed values are redacted in tool output when the value is specific enough. Provider credentials stay out of sandboxed commands.'
          }),
          jsxs('label', {
            className: 'flex items-center gap-2 text-xs text-muted-foreground',
            children: [
              jsx(Checkbox, {
                checked: tell && !!sessionId,
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
  const hostsDialog = useDialogHost()

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
      hostsDialog ? jsx(SecretDropDialog, { rest }) : null
    ]
  })
}

export default {
  id: 'secret-drop',
  name: 'Secret drop',
  description: 'Store a secret on the gateway host without showing it to the model',
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
