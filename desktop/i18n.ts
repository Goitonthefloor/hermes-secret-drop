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

export const zh: SecretDropMessages = {
  dialog: {
    title: '给 Hermes 一个密钥',
    description:
      '该值会写入网关主机上的文件，保存为环境变量，随后文件会被删除。它不会加入聊天，模型也永远看不到它。'
  },
  labels: {
    variableName: '变量名',
    secret: '密钥',
    hint:
      '后续命令可以使用 $NAME。当值足够具体时，工具输出中的打印值会被脱敏。提供商凭据不会进入沙箱命令。',
    tellHermes: '告诉 Hermes 变量名'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: '已隐藏'
  },
  buttons: {
    cancel: '取消',
    store: '存储密钥',
    storing: '正在存储…'
  },
  error: {
    name: '请使用类似 DEPLOY_PASSWORD 的变量名。',
    generic: '无法存储密钥',
    noSession:
      '密钥已存储，但没有打开的聊天来告知变量名。',
    tellFailed:
      '密钥已存储，但未告知 Hermes 变量名。'
  },
  success: {
    storedAs: (stored: string) => `已存储为 ${stored}。`,
    modelNotShown: '模型未见过该值。',
    notPassthrough: '它不会转发到沙箱命令中。',
    redactedFalse: '工具输出不会脱敏此值。',
    indexedFalse: '后续会话可能无法脱敏它。'
  },
  modelNote: {
    prefix: (stored: string) =>
      `我已将密钥存储在环境变量 ${stored} 中。`,
    passthrough: (stored: string) => `在命令中使用 $${stored}。`,
    sandbox: '沙箱命令不会收到它。',
    redactYes:
      '不要让我粘贴该值，也不要打印它。',
    redactNo:
      '不要让我粘贴、打印或编码该值。工具输出不会脱敏它。'
  },
  palette: {
    open: '给 Hermes 一个密钥',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

export const zhHant: SecretDropMessages = {
  dialog: {
    title: '給 Hermes 一個密鑰',
    description:
      '該值會寫入閘道主機上的檔案，儲存為環境變數，隨後檔案會被刪除。它不會加入聊天，模型也永遠看不到它。'
  },
  labels: {
    variableName: '變數名稱',
    secret: '密鑰',
    hint:
      '後續命令可以使用 $NAME。當值足夠具體時，工具輸出中的列印值會被脫敏。提供商憑證不會進入沙箱命令。',
    tellHermes: '告訴 Hermes 變數名稱'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: '已隱藏'
  },
  buttons: {
    cancel: '取消',
    store: '儲存密鑰',
    storing: '正在儲存…'
  },
  error: {
    name: '請使用類似 DEPLOY_PASSWORD 的變數名稱。',
    generic: '無法儲存密鑰',
    noSession:
      '密鑰已儲存，但沒有開啟的聊天來告知變數名稱。',
    tellFailed:
      '密鑰已儲存，但未告知 Hermes 變數名稱。'
  },
  success: {
    storedAs: (stored: string) => `已儲存為 ${stored}。`,
    modelNotShown: '模型未見過該值。',
    notPassthrough: '它不會轉發到沙箱命令中。',
    redactedFalse: '工具輸出不會脫敏此值。',
    indexedFalse: '後續工作階段可能無法脫敏它。'
  },
  modelNote: {
    prefix: (stored: string) =>
      `我已將密鑰儲存在環境變數 ${stored} 中。`,
    passthrough: (stored: string) => `在命令中使用 $${stored}。`,
    sandbox: '沙箱命令不會收到它。',
    redactYes:
      '不要讓我貼上該值，也不要列印它。',
    redactNo:
      '不要讓我貼上、列印或編碼該值。工具輸出不會脫敏它。'
  },
  palette: {
    open: '給 Hermes 一個密鑰',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

export const ja: SecretDropMessages = {
  dialog: {
    title: 'Hermes にシークレットを渡す',
    description:
      '値はゲートウェイホスト上のファイルに書き込まれ、環境変数として保存された後、ファイルは削除されます。チャットには追加されず、モデルがそれを見ることはありません。'
  },
  labels: {
    variableName: '変数名',
    secret: 'シークレット',
    hint:
      '後続のコマンドでは $NAME を使用できます。値が十分に具体的な場合、ツール出力内の表示値はマスキングされます。プロバイダーの認証情報はサンドボックスコマンドに渡りません。',
    tellHermes: 'Hermes に変数名を伝える'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: '非表示'
  },
  buttons: {
    cancel: 'キャンセル',
    store: 'シークレットを保存',
    storing: '保存中…'
  },
  error: {
    name: 'DEPLOY_PASSWORD のような変数名を使用してください。',
    generic: 'シークレットを保存できませんでした',
    noSession:
      'シークレットは保存されましたが、変数名を伝える開いているチャットがありません。',
    tellFailed:
      'シークレットは保存されましたが、Hermes に変数名が伝えられませんでした。'
  },
  success: {
    storedAs: (stored: string) => `${stored} として保存しました。`,
    modelNotShown: 'モデルには値は表示されていません。',
    notPassthrough: 'サンドボックスコマンドには転送されません。',
    redactedFalse: 'ツール出力はこの値をマスキングしません。',
    indexedFalse: '後のセッションではマスキングできない可能性があります。'
  },
  modelNote: {
    prefix: (stored: string) =>
      `環境変数 ${stored} にシークレットを保存しました。`,
    passthrough: (stored: string) => `コマンドでは $${stored} を使用してください。`,
    sandbox: 'サンドボックスコマンドには渡されません。',
    redactYes:
      '値の貼り付けを求めず、出力もしないでください。',
    redactNo:
      '値の貼り付け、出力、エンコードを求めないでください。ツール出力はマスキングしません。'
  },
  palette: {
    open: 'Hermes にシークレットを渡す',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

export const ar: SecretDropMessages = {
  dialog: {
    title: 'أعطِ Hermes سرًا',
    description:
      'تُكتب القيمة في ملف على مضيف البوابة، وتُحفظ كمتغير بيئة، ثم يُحذف الملف. لا تُضاف إلى الدردشة، ولا يراها النموذج أبدًا.'
  },
  labels: {
    variableName: 'اسم المتغير',
    secret: 'السر',
    hint:
      'يمكن للأوامر اللاحقة استخدام $NAME. تُحجب القيم المطبوعة في مخرجات الأدوات عندما تكون القيمة محددة بما يكفي. تبقى بيانات اعتماد الموفر خارج الأوامر المعزولة.',
    tellHermes: 'أخبر Hermes باسم المتغير'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: 'مخفي'
  },
  buttons: {
    cancel: 'إلغاء',
    store: 'تخزين السر',
    storing: 'جارٍ التخزين…'
  },
  error: {
    name: 'استخدم اسم متغير مثل DEPLOY_PASSWORD.',
    generic: 'تعذر تخزين السر',
    noSession:
      'تم تخزين السر، لكن لا توجد محادثة مفتوحة لإخبار اسم المتغير.',
    tellFailed:
      'تم تخزين السر، لكن لم يُخبر Hermes باسم المتغير.'
  },
  success: {
    storedAs: (stored: string) => `تم التخزين باسم ${stored}.`,
    modelNotShown: 'لم يُعرض النموذج القيمة.',
    notPassthrough: 'لا يُمرَّر إلى الأوامر المعزولة.',
    redactedFalse: 'لن تحجب مخرجات الأدوات هذه القيمة.',
    indexedFalse: 'قد لا تتمكن جلسة لاحقة من حجبها.'
  },
  modelNote: {
    prefix: (stored: string) =>
      `خزّنت سرًا في متغير البيئة ${stored}.`,
    passthrough: (stored: string) => `استخدم $${stored} في الأوامر.`,
    sandbox: 'الأوامر المعزولة لا تستلمها.',
    redactYes:
      'لا تطلب مني لصق القيمة، ولا تطبعها.',
    redactNo:
      'لا تطلب مني لصق القيمة أو طباعتها أو ترميزها. لن تحجب مخرجات الأدوات هذه القيمة.'
  },
  palette: {
    open: 'أعطِ Hermes سرًا',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

export const ru: SecretDropMessages = {
  dialog: {
    title: 'Передать Hermes секрет',
    description:
      'Значение записывается в файл на хосте шлюза, сохраняется как переменная окружения, после чего файл удаляется. Оно не добавляется в чат, и модель его никогда не видит.'
  },
  labels: {
    variableName: 'Имя переменной',
    secret: 'Секрет',
    hint:
      'Последующие команды могут использовать $NAME. Выводимые значения маскируются в результатах инструментов, если значение достаточно специфично. Учётные данные провайдера не попадают в изолированные команды.',
    tellHermes: 'Сообщить Hermes имя переменной'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: 'Скрыто'
  },
  buttons: {
    cancel: 'Отмена',
    store: 'Сохранить секрет',
    storing: 'Сохранение…'
  },
  error: {
    name: 'Используйте имя переменной вроде DEPLOY_PASSWORD.',
    generic: 'Не удалось сохранить секрет',
    noSession:
      'Секрет сохранён, но нет открытого чата, чтобы сообщить имя переменной.',
    tellFailed:
      'Секрет сохранён, но Hermes не было сообщено имя переменной.'
  },
  success: {
    storedAs: (stored: string) => `Сохранено как ${stored}.`,
    modelNotShown: 'Модель не видела это значение.',
    notPassthrough: 'Оно не передаётся в изолированные команды.',
    redactedFalse: 'Вывод инструментов не будет маскировать это значение.',
    indexedFalse: 'Позже сессия может не суметь его замаскировать.'
  },
  modelNote: {
    prefix: (stored: string) =>
      `Я сохранил секрет в переменной окружения ${stored}.`,
    passthrough: (stored: string) => `Используйте $${stored} в командах.`,
    sandbox: 'Изолированные команды его не получают.',
    redactYes:
      'Не просите меня вставить значение и не выводите его.',
    redactNo:
      'Не просите меня вставить, вывести или закодировать значение. Вывод инструментов не будет его маскировать.'
  },
  palette: {
    open: 'Передать Hermes секрет',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

export const fr: SecretDropMessages = {
  dialog: {
    title: 'Donner un secret à Hermes',
    description:
      'La valeur est écrite dans un fichier sur l’hôte de la passerelle, enregistrée comme variable d’environnement, puis le fichier est supprimé. Elle n’est pas ajoutée au chat, et le modèle ne la voit jamais.'
  },
  labels: {
    variableName: 'Nom de la variable',
    secret: 'Secret',
    hint:
      'Les commandes ultérieures peuvent utiliser $NAME. Les valeurs affichées sont masquées dans la sortie des outils lorsque la valeur est suffisamment spécifique. Les identifiants du fournisseur restent hors des commandes en bac à sable.',
    tellHermes: 'Indiquer le nom de la variable à Hermes'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: 'Masqué'
  },
  buttons: {
    cancel: 'Annuler',
    store: 'Enregistrer le secret',
    storing: 'Enregistrement…'
  },
  error: {
    name: 'Utilisez un nom de variable comme DEPLOY_PASSWORD.',
    generic: 'Impossible d’enregistrer le secret',
    noSession:
      'Le secret est enregistré, mais aucun chat ouvert ne permet d’indiquer le nom de la variable.',
    tellFailed:
      'Le secret est enregistré, mais Hermes n’a pas reçu le nom de la variable.'
  },
  success: {
    storedAs: (stored: string) => `Enregistré sous ${stored}.`,
    modelNotShown: 'Le modèle n’a pas vu la valeur.',
    notPassthrough: 'Elle n’est pas transmise aux commandes en bac à sable.',
    redactedFalse: 'La sortie des outils ne masquera pas cette valeur.',
    indexedFalse: 'Une session ultérieure risque de ne pas pouvoir la masquer.'
  },
  modelNote: {
    prefix: (stored: string) =>
      `J’ai enregistré un secret dans la variable d’environnement ${stored}.`,
    passthrough: (stored: string) => `Utilisez $${stored} dans les commandes.`,
    sandbox: 'Les commandes en bac à sable ne la reçoivent pas.',
    redactYes:
      'Ne me demandez pas de coller la valeur, et ne l’affichez pas.',
    redactNo:
      'Ne me demandez pas de coller, d’afficher ou d’encoder la valeur. La sortie des outils ne la masquera pas.'
  },
  palette: {
    open: 'Donner un secret à Hermes',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

export const es: SecretDropMessages = {
  dialog: {
    title: 'Dar un secreto a Hermes',
    description:
      'El valor se escribe en un archivo en el host de la pasarela, se guarda como variable de entorno y luego se elimina el archivo. No se añade al chat, y el modelo nunca lo ve.'
  },
  labels: {
    variableName: 'Nombre de la variable',
    secret: 'Secreto',
    hint:
      'Los comandos posteriores pueden usar $NAME. Los valores impresos se ocultan en la salida de las herramientas cuando el valor es lo bastante específico. Las credenciales del proveedor no entran en los comandos aislados.',
    tellHermes: 'Decir a Hermes el nombre de la variable'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    secret: 'Oculto'
  },
  buttons: {
    cancel: 'Cancelar',
    store: 'Guardar secreto',
    storing: 'Guardando…'
  },
  error: {
    name: 'Usa un nombre de variable como DEPLOY_PASSWORD.',
    generic: 'No se pudo guardar el secreto',
    noSession:
      'El secreto está guardado, pero no hay un chat abierto para indicar el nombre de la variable.',
    tellFailed:
      'El secreto está guardado, pero no se indicó a Hermes el nombre de la variable.'
  },
  success: {
    storedAs: (stored: string) => `Guardado como ${stored}.`,
    modelNotShown: 'El modelo no vio el valor.',
    notPassthrough: 'No se reenvía a los comandos aislados.',
    redactedFalse: 'La salida de las herramientas no ocultará este valor.',
    indexedFalse: 'Una sesión posterior podría no poder ocultarlo.'
  },
  modelNote: {
    prefix: (stored: string) =>
      `He guardado un secreto en la variable de entorno ${stored}.`,
    passthrough: (stored: string) => `Usa $${stored} en los comandos.`,
    sandbox: 'Los comandos aislados no lo reciben.',
    redactYes:
      'No me pidas pegar el valor ni lo imprimas.',
    redactNo:
      'No me pidas pegar, imprimir ni codificar el valor. La salida de las herramientas no lo ocultará.'
  },
  palette: {
    open: 'Dar un secreto a Hermes',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

// ── Bundle-Export (plug-in-typisiert) ───────────────────────────────────────

export const SECRET_DROP_LOCALES: PluginLocaleBundles = {
  en,
  de,
  zh,
  'zh-hant': zhHant,
  ja,
  ar,
  ru,
  fr,
  es
}

// ── React-Helper (wie im Kanban-Plugin üblich) ──────────────────────────────

export function useSecretDropI18n(): PluginTranslate {
  return usePluginI18n('secret-drop')
}
