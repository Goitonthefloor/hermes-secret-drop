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
  useValue,
  usePluginI18n
} from '@hermes/plugin-sdk'
import { SECRET_DROP_LOCALES } from './i18n'

const $open = atom(false)
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/
const HOST_EVENT = 'secret-drop-dialog-host'
let dialogHost = 0
let nextDialogHost = 0

function openDialog() {
  $open.set(true)
}

function failureMessage(error, secret, t) {
  const message = error && typeof error.message === 'string' ? error.message.trim() : ''

  if (!message || message.length > 300 || (secret && message.includes(secret))) {
    return t('error.generic')
  }

  return message
}

function successMessage(stored, result, t) {
  const parts = [t('success.storedAs', stored), t('success.modelNotShown')]

  if (result && result.passthrough === false) {
    parts.push(t('success.notPassthrough'))
  }

  if (result && result.redacted === false) {
    parts.push(t('success.redactedFalse'))
  }

  if (result && result.indexed === false) {
    parts.push(t('success.indexedFalse'))
  }

  return parts.join(' ')
}

function modelNote(stored, result, t) {
  const passthrough = !result || result.passthrough !== false
  const redacted = !result || result.redacted !== false
  const use = passthrough
    ? t('modelNote.passthrough', stored)
    : t('modelNote.sandbox')
  const redact = redacted
    ? t('modelNote.redactYes')
    : t('modelNote.redactNo')

  return `${t('modelNote.prefix', stored)} ${use} ${redact}`
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
  const t = usePluginI18n('secret-drop')

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
      host.notify({ kind: 'warning', message: t('error.name') })

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
      host.notify({ kind: 'error', message: failureMessage(error, secret, t) })
      setSubmitting(false)

      return
    }

    setValue('')
    setSubmitting(false)
    $open.set(false)

    const stored = (result && result.stored_as) || secretName

    host.notify({ kind: 'success', message: successMessage(stored, result, t) })

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
        message: t('error.noSession')
      })

      return
    }

    try {
      const sent = host.composer.submit(session, modelNote(stored, result, t))

      if (!sent) {
        host.notify({
          kind: 'warning',
          message: t('error.tellFailed')
        })
      }
    } catch {
      host.notify({
        kind: 'warning',
        message: t('error.tellFailed')
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
              jsx(DialogTitle, { children: t('dialog.title') }),
              jsx(DialogDescription, {
                children: t('dialog.description')
              })
            ]
          }),
          jsxs('label', {
            className: 'grid gap-1 text-xs',
            children: [
              t('labels.variableName'),
              jsx(Input, {
                autoComplete: 'off',
                autoFocus: true,
                disabled: submitting,
                onChange: event => setName(event.target.value),
                placeholder: t('placeholders.variableName'),
                spellCheck: false,
                value: name
              })
            ]
          }),
          jsxs('label', {
            className: 'grid gap-1 text-xs',
            children: [
              t('labels.secret'),
              jsx(Input, {
                autoComplete: 'new-password',
                disabled: submitting,
                onChange: event => setValue(event.target.value),
                placeholder: t('placeholders.secret'),
                spellCheck: false,
                type: 'password',
                value: value
              })
            ]
          }),
          jsx('p', {
            className: 'text-xs text-muted-foreground',
            children: t('labels.hint')
          }),
          jsxs('label', {
            className: 'flex items-center gap-2 text-xs text-muted-foreground',
            children: [
              jsx(Checkbox, {
                checked: tell && !!sessionId,
                disabled: submitting || !sessionId,
                onCheckedChange: checked => setTell(checked === true)
              }),
              t('labels.tellHermes')
            ]
          }),
          jsxs(DialogFooter, {
            children: [
              jsx(Button, {
                disabled: submitting,
                onClick: () => $open.set(false),
                type: 'button',
                variant: 'ghost',
                children: t('buttons.cancel')
              }),
              jsx(Button, {
                disabled: submitting || !value || !name.trim(),
                type: 'submit',
                children: submitting ? t('buttons.storing') : t('buttons.store')
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
  defaultEnabled: true,
  register(ctx) {
    const rest = (path, opts) => ctx.rest(path, opts)
    const t = ctx.i18n.t

    ctx.i18n.register(SECRET_DROP_LOCALES)

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
        label: t('palette.open'),
        keywords: t('palette.keywords'),
        run: () => openDialog()
      }
    })
  }
}
