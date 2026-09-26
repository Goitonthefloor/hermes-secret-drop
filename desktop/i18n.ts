/**
 * Plugin-scoped i18n for secret-drop — bundles shipped under the plugin id
 * via `ctx.i18n.register` (#67303 pattern), never touching core en.ts.
 * `usePluginI18n('secret-drop')` returns a stringly-typed t(key, …).
 *
 * Locales shipped: en (source), de. All other Hermes Desktop locales
 * (zh, zh-hant, ja, ar, ru, fr, es) fall back to English automatically.
 */

import { type PluginLocaleBundles, type PluginTranslate, usePluginI18n } from '@hermes/plugin-sdk'
import { useMemo } from 'react'

// ── Message shape (flat-ish, grouped by UI section; dot-addressed) ──────────

export type SecretDropMessages = {
  dialog: {
    title: string
    description: string
  }
  labels: {
    variableName: string
    secret: string
    hint: string
    tellHermes: string
  }
  placeholders: {
    variableName: string
    secret: string
  }
  buttons: {
    cancel: string
    store: string
    storing: string
  }
  error: {
    name: string
    generic: string
    noSession: string
    tellFailed: string
  }
  success: {
    storedAs: (stored: string) => string
    modelNotShown: string
    notPassthrough: string
    redactedFalse: string
    indexedFalse: string
  }
  modelNote: {
    prefix: (stored: string) => string
    passthrough: (stored: string) => string
    sandbox: string
    redactYes: string
    redactNo: string
  }
  palette: {
    open: string
    keywords: string[]
  }
}

// ── English (source) ────────────────────────────────────────────────────────

export const en: SecretDropMessages = {
  dialog: {
    title: 'Give Hermes a secret',
    description:
      'The value is written to a file on the gateway host, saved as an environment variable, and the file is deleted. It is not added to the chat, and the model never sees it.'
  },
  labels: {
    variableName: 'Variable name',
    secret: 'Secret',
    hint:
      'Later commands can use $NAME. Printed values are redacted in tool output when the value is specific enough. Provider credentials stay out of sandboxed commands.',
    tellHermes: 'Tell Hermes the variable name'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: 'Hidden'
  },
  buttons: {
    cancel: 'Cancel',
    store: 'Store secret',
    storing: 'Storing…'
  },
  error: {
    name: 'Use a variable name like DEPLOY_PASSWORD.',
    generic: 'Could not store the secret',
    noSession:
      'The secret is stored, but there is no open chat to tell the variable name.',
    tellFailed:
      'The secret is stored, but Hermes was not told the variable name.'
  },
  success: {
    storedAs: (stored: string) => `Stored as ${stored}.`,
    modelNotShown: 'The model was not shown the value.',
    notPassthrough: 'It is not forwarded into sandboxed commands.',
    redactedFalse: 'Tool output will not redact this value.',
    indexedFalse: 'A later session may not redact it.'
  },
  modelNote: {
    prefix: (stored: string) =>
      `I stored a secret in the environment variable ${stored}.`,
    passthrough: (stored: string) => `Use $${stored} in commands.`,
    sandbox: 'Sandboxed commands do not receive it.',
    redactYes:
      'Do not ask me to paste the value, and do not print it.',
    redactNo:
      'Do not ask me to paste the value, print it, or encode it. Tool output will not redact it.'
  },
  palette: {
    open: 'Give Hermes a secret',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

// ── Deutsch ─────────────────────────────────────────────────────────

export const de: SecretDropMessages = {
  dialog: {
    title: 'Gib Hermes ein Geheimnis',
    description:
      'Der Wert wird auf dem Gateway-Host in eine Datei geschrieben, als Umgebungsvariable gespeichert und die Datei anschließend gelöscht. Er wird nicht in den Chat eingefügt und das Modell sieht ihn nie.'
  },
  labels: {
    variableName: 'Variablenname',
    secret: 'Geheimnis',
    hint:
      'Spätere Befehle können $NAME verwenden. Ausgabe wird in Tool-Ergebnissen rotiert, sobald der Wert spezifisch genug ist. Anbieter-Zugangsdaten bleiben von sandboxed Befehlen ausgeschlossen.',
    tellHermes: 'Hermes die Variablenname mitteilen'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: 'Versteckt'
  },
  buttons: {
    cancel: 'Abbrechen',
    store: 'Geheimnis speichern',
    storing: 'Wird gespeichert…'
  },
  error: {
    name: 'Verwende einen Variablennamen wie DEPLOY_PASSWORD.',
    generic: 'Das Geheimnis konnte nicht gespeichert werden.',
    noSession:
      'Das Geheimnis ist gespeichert, aber es ist kein offener Chat offen, um den Variablennamen mitzuteilen.',
    tellFailed:
      'Das Geheimnis ist gespeichert, aber Hermes wurde der Variablenname nicht mitgeteilt.'
  },
  success: {
    storedAs: (stored: string) => `Gespeichert als ${stored}.`,
    modelNotShown: 'Das Modell hat den Wert nicht gesehen.',
    notPassthrough: 'Er wird nicht in sandboxed Befehle weitergeleitet.',
    redactedFalse: 'Tool-Ausgabe wird diesen Wert nicht rotieren.',
    indexedFalse: 'Eine spätere Sitzung kann ihn möglicherweise nicht rotieren.'
  },
  modelNote: {
    prefix: (stored: string) =>
      `Ich habe ein Geheimnis in der Umgebungsvariable ${stored} gespeichert.`,
    passthrough: (stored: string) => `Verwende $${stored} in Befehlen.`,
    sandbox: 'Sandboxed Befehle erhalten ihn nicht.',
    redactYes:
      'Bitte nicht mich bitten, den Wert einzufügen, und nicht ihn ausgeben.',
    redactNo:
      'Bitte nicht mich bitten, den Wert einzufügen, auszugeben oder zu kodieren. Tool-Ausgabe wird ihn nicht rotieren.'
  },
  palette: {
    open: 'Gib Hermes ein Geheimnis',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

// ── Bundle-Export (plug-in-typisiert) ───────────────────────────────────────

export const SECRET_DROP_LOCALES: PluginLocaleBundles = { en, de }

// ── React-Helper (wie im Kanban-Plugin üblich) ──────────────────────────────

export function useSecretDropI18n(): PluginTranslate {
  return usePluginI18n('secret-drop')
}
