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

// Locales live in this file. Hermes evaluates plugin.js as one blob and
// rejects every import except @hermes/plugin-sdk and react, so a sibling
// i18n module never loads.

const en = {
  dialog: {
    title: 'Give Hermes a secret',
    description:
      'The value is stored on the gateway host as an environment variable. It is not added to the chat; commands use {{secret:NAME}} and the gateway inserts the value when it runs them. Direct reads of the stored file are blocked in tool calls, and tool output is scrubbed for values specific enough to match.'
  },
  labels: {
    variableName: 'Variable name',
    username: 'Username (optional)',
    secret: 'Secret',
    hint:
      'Commands use {{secret:NAME}}; the gateway substitutes the value when it runs them. Direct reads of the stored value are blocked in tool calls. Provider credentials are stored but not injected.',
    tellHermes: 'Tell Hermes the variable name'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `Stored as ${stored}.`,
    valueIsolated: 'The value is not added to the chat; use {{secret:NAME}} in commands. Tool output is scrubbed for it when it is specific enough to match.',
    notPassthrough: 'It is not forwarded into sandboxed commands.',
    redactedFalse: 'Tool output will not redact this value.',
    indexedFalse: 'A later session may not redact it.'
  },
  modelNote: {
    prefix: (stored) =>
      `I stored a secret in the environment variable ${stored}.`,
    passthrough: (stored) => `Use {{secret:${stored}}} in commands.`,
    sandbox: 'Sandboxed commands do not receive it.',
    username: (target) => `The username is stored as ${target}; use {{secret:${target}}}} for it.`,
    redactYes:
      'Do not ask me to paste, print, copy, or encode the value.',
    redactNo:
      'Do not ask me to paste, print, copy, or encode the value. Tool output will not scrub it.'
  },
  palette: {
    open: 'Give Hermes a secret',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

// ── Deutsch ─────────────────────────────────────────────────────────

const de = {
  dialog: {
    title: 'Gib Hermes ein Geheimnis',
    description:
      'Der Wert wird auf dem Gateway-Host als Umgebungsvariable gespeichert. Er wird nicht in den Chat übernommen; Befehle nutzen {{secret:NAME}}, und das Gateway setzt den Wert beim Ausführen ein. Direkte Leseversuche der Speicherdatei werden in Tool-Aufrufen blockiert, und Tool-Ausgaben werden für Werte gescrubbt, die eindeutig genug sind.'
  },
  labels: {
    variableName: 'Variablenname',
    username: 'Benutzername (optional)',
    secret: 'Geheimnis',
    hint:
      'Befehle nutzen {{secret:NAME}}; das Gateway setzt den Wert beim Ausführen ein. Direkte Leseversuche des gespeicherten Werts werden in Tool-Aufrufen blockiert. Anbieter-Zugangsdaten werden gespeichert, aber nicht eingesetzt.',
    tellHermes: 'Hermes die Variablenname mitteilen'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `Gespeichert als ${stored}.`,
    valueIsolated: 'Der Wert wird nicht in den Chat übernommen; verwende {{secret:NAME}} in Befehlen. Tool-Ausgaben werden für ihn gescrubbt, wenn er eindeutig genug ist.',
    notPassthrough: 'Er wird nicht in sandboxed Befehle weitergeleitet.',
    redactedFalse: 'Tool-Ausgabe wird diesen Wert nicht rotieren.',
    indexedFalse: 'Eine spätere Sitzung kann ihn möglicherweise nicht rotieren.'
  },
  modelNote: {
    prefix: (stored) =>
      `Ich habe ein Geheimnis in der Umgebungsvariable ${stored} gespeichert.`,
    passthrough: (stored) => `Verwende {{secret:${stored}}} in Befehlen.`,
    sandbox: 'Sandboxed Befehle erhalten ihn nicht.',
    username: (target) => `Der Benutzername ist als ${target} gespeichert; verwende {{secret:${target}}}} dafür.`,
    redactYes:
      'Bitte nicht nach dem Wert fragen und ihn nicht ausgeben, kopieren oder kodieren.',
    redactNo:
      'Bitte nicht nach dem Wert fragen und ihn nicht ausgeben, kopieren oder kodieren. Die Tool-Ausgabe bereinigt ihn nicht.'
  },
  palette: {
    open: 'Gib Hermes ein Geheimnis',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

const zh = {
  dialog: {
    title: '给 Hermes 一个密钥',
    description:
      '该值会作为环境变量保存在网关主机上。它不会被加入聊天；命令使用 {{secret:NAME}}，网关在执行时填入该值。工具调用中直接读取该存储文件会被阻止，工具输出中足够具体的值会被擦除。'
  },
  labels: {
    variableName: '变量名',
    username: '用户名（可选）',
    secret: '密钥',
    hint:
      '命令使用 {{secret:NAME}}；网关在执行时替换为该值。工具调用中直接读取该值会被阻止。提供商凭据会被保存，但不会被注入。',
    tellHermes: '告诉 Hermes 变量名'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `已存储为 ${stored}。`,
    valueIsolated: '该值不会被加入聊天；请在命令中使用 {{secret:NAME}}。当该值足够具体时，工具输出中的它会被擦除。',
    notPassthrough: '它不会转发到沙箱命令中。',
    redactedFalse: '工具输出不会脱敏此值。',
    indexedFalse: '后续会话可能无法脱敏它。'
  },
  modelNote: {
    prefix: (stored) =>
      `我已将密钥存储在环境变量 ${stored} 中。`,
    passthrough: (stored) => `在命令中使用 {{secret:${stored}}}。`,
    sandbox: '沙箱命令不会收到它。',
    username: (target) => `用户名已保存为 ${target}；使用 {{secret:${target}}}} 引用它。`,
    redactYes:
      '不要让我粘贴该值，也不要打印、复制或编码它。',
    redactNo:
      '不要让我粘贴、打印、复制或编码该值。工具输出不会清理它。'
  },
  palette: {
    open: '给 Hermes 一个密钥',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

const zhHant = {
  dialog: {
    title: '給 Hermes 一個密鑰',
    description:
      '該值會作為環境變數儲存在閘道主機上。它不會被加入聊天；命令使用 {{secret:NAME}}，閘道在執行時填入該值。工具呼叫中直接讀取該儲存檔案會被阻止，工具輸出中足夠具體的值會被擦除。'
  },
  labels: {
    variableName: '變數名稱',
    username: '使用者名稱（選填）',
    secret: '密鑰',
    hint:
      '命令使用 {{secret:NAME}}；閘道在執行時替換為該值。工具呼叫中直接讀取該值會被阻止。提供商憑證會被儲存，但不會被注入。',
    tellHermes: '告訴 Hermes 變數名稱'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `已儲存為 ${stored}。`,
    valueIsolated: '該值不會被加入聊天；請在命令中使用 {{secret:NAME}}。當該值足夠具體時，工具輸出中的它會被擦除。',
    notPassthrough: '它不會轉發到沙箱命令中。',
    redactedFalse: '工具輸出不會脫敏此值。',
    indexedFalse: '後續工作階段可能無法脫敏它。'
  },
  modelNote: {
    prefix: (stored) =>
      `我已將密鑰儲存在環境變數 ${stored} 中。`,
    passthrough: (stored) => `在命令中使用 {{secret:${stored}}}。`,
    sandbox: '沙箱命令不會收到它。',
    username: (target) => `使用者名稱已儲存為 ${target}；使用 {{secret:${target}}}} 引用它。`,
    redactYes:
      '不要讓我貼上該值，也不要列印、複製或編碼它。',
    redactNo:
      '不要讓我貼上、列印、複製或編碼該值。工具輸出不會清理它。'
  },
  palette: {
    open: '給 Hermes 一個密鑰',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

const ja = {
  dialog: {
    title: 'Hermes にシークレットを渡す',
    description:
      '値はゲートウェイホストに環境変数として保存されます。チャットには追加されません。コマンドでは {{secret:NAME}} を使い、ゲートウェイが実行時に値を挿入します。保存ファイルの直接読み取りはツール呼び出しでブロックされ、ツール出力内の十分に特定可能な値は伏せられます。'
  },
  labels: {
    variableName: '変数名',
    username: 'ユーザー名（任意）',
    secret: 'シークレット',
    hint:
      'コマンドでは {{secret:NAME}} を使用します。ゲートウェイが実行時に値を置き換えます。ツール呼び出しで保存値を直接読むことはブロックされます。プロバイダーの認証情報は保存されますが挿入されません。',
    tellHermes: 'Hermes に変数名を伝える'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `${stored} として保存しました。`,
    valueIsolated: '値はチャットに追加されません。コマンドでは {{secret:NAME}} を使用してください。十分に特定可能な場合、ツール出力ではその値が伏せられます。',
    notPassthrough: 'サンドボックスコマンドには転送されません。',
    redactedFalse: 'ツール出力はこの値をマスキングしません。',
    indexedFalse: '後のセッションではマスキングできない可能性があります。'
  },
  modelNote: {
    prefix: (stored) =>
      `環境変数 ${stored} にシークレットを保存しました。`,
    passthrough: (stored) => `コマンドでは {{secret:${stored}}} を使用してください。`,
    sandbox: 'サンドボックスコマンドには渡されません。',
    username: (target) => `ユーザー名は ${target} として保存されました。{{secret:${target}}}} で参照してください。`,
    redactYes:
      '値の貼り付け、出力、コピー、エンコードを求めないでください。',
    redactNo:
      '値の貼り付け、出力、コピー、エンコードを求めないでください。ツール出力はそれを消去しません。'
  },
  palette: {
    open: 'Hermes にシークレットを渡す',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

const ar = {
  dialog: {
    title: 'أعطِ Hermes سرًا',
    description:
      'تُحفظ القيمة على مضيف البوابة كمتغير بيئة. لا تُضاف إلى الدردشة؛ تستخدم الأوامر {{secret:NAME}} وتُدرج البوابة القيمة عند التنفيذ. تُحظر قراءة ملف التخزين مباشرة في استدعاءات الأدوات، وتُحجب القيم المحددة بما يكفي في مخرجات الأدوات.'
  },
  labels: {
    variableName: 'اسم المتغير',
    username: 'اسم المستخدم (اختياري)',
    secret: 'السر',
    hint:
      'تستخدم الأوامر {{secret:NAME}}؛ وتستبدل البوابة القيمة عند التنفيذ. تُحظر قراءة القيمة المخزنة مباشرة في استدعاءات الأدوات. تُحفظ بيانات اعتماد الموفر ولا تُدرج.',
    tellHermes: 'أخبر Hermes باسم المتغير'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `تم التخزين باسم ${stored}.`,
    valueIsolated: 'لا تُضاف القيمة إلى الدردشة؛ استخدم {{secret:NAME}} في الأوامر. تُحجب القيمة في مخرجات الأدوات عندما تكون محددة بما يكفي.',
    notPassthrough: 'لا يُمرَّر إلى الأوامر المعزولة.',
    redactedFalse: 'لن تحجب مخرجات الأدوات هذه القيمة.',
    indexedFalse: 'قد لا تتمكن جلسة لاحقة من حجبها.'
  },
  modelNote: {
    prefix: (stored) =>
      `خزّنت سرًا في متغير البيئة ${stored}.`,
    passthrough: (stored) => `استخدم {{secret:${stored}}} في الأوامر.`,
    sandbox: 'الأوامر المعزولة لا تستلمها.',
    username: (target) => `يُحفظ اسم المستخدم باسم ${target}؛ استخدم {{secret:${target}}}} له.`,
    redactYes:
      'لا تطلب مني لصق القيمة أو طباعتها أو نسخها أو ترميزها.',
    redactNo:
      'لا تطلب مني لصق القيمة أو طباعتها أو نسخها أو ترميزها. لن تحذفها مخرجات الأدوات.'
  },
  palette: {
    open: 'أعطِ Hermes سرًا',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

const ru = {
  dialog: {
    title: 'Передать Hermes секрет',
    description:
      'Значение хранится на хосте шлюза как переменная окружения. Оно не добавляется в чат; команды используют {{secret:NAME}}, а шлюз подставляет значение при выполнении. Прямое чтение файла хранилища в вызовах инструментов блокируется, а достаточно специфичные значения скрываются в выводе инструментов.'
  },
  labels: {
    variableName: 'Имя переменной',
    username: 'Имя пользователя (необязательно)',
    secret: 'Секрет',
    hint:
      'Команды используют {{secret:NAME}}; шлюз подставляет значение при выполнении. Прямое чтение сохранённого значения в вызовах инструментов блокируется. Учётные данные провайдера сохраняются, но не подставляются.',
    tellHermes: 'Сообщить Hermes имя переменной'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `Сохранено как ${stored}.`,
    valueIsolated: 'Значение не добавляется в чат; используйте {{secret:NAME}} в командах. В выводе инструментов оно скрывается, если достаточно специфично.',
    notPassthrough: 'Оно не передаётся в изолированные команды.',
    redactedFalse: 'Вывод инструментов не будет маскировать это значение.',
    indexedFalse: 'Позже сессия может не суметь его замаскировать.'
  },
  modelNote: {
    prefix: (stored) =>
      `Я сохранил секрет в переменной окружения ${stored}.`,
    passthrough: (stored) => `Используйте {{secret:${stored}}} в командах.`,
    sandbox: 'Изолированные команды его не получают.',
    username: (target) => `Имя пользователя сохранено как ${target}; используйте {{secret:${target}}}}.`,
    redactYes:
      'Не просите меня вставить, вывести, скопировать или закодировать значение.',
    redactNo:
      'Не просите меня вставить, вывести, скопировать или закодировать значение. Вывод инструментов не будет его вычищать.'
  },
  palette: {
    open: 'Передать Hermes секрет',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

const fr = {
  dialog: {
    title: 'Donner un secret à Hermes',
    description:
      'La valeur est stockée sur l’hôte de la passerelle comme variable d’environnement. Elle n’est pas ajoutée au chat ; les commandes utilisent {{secret:NAME}} et la passerelle insère la valeur à l’exécution. La lecture directe du fichier de stockage est bloquée dans les appels d’outils, et les valeurs suffisamment spécifiques sont masquées dans la sortie des outils.'
  },
  labels: {
    variableName: 'Nom de la variable',
    username: 'Nom d’utilisateur (facultatif)',
    secret: 'Secret',
    hint:
      'Les commandes utilisent {{secret:NAME}} ; la passerelle substitue la valeur à l’exécution. La lecture directe de la valeur stockée est bloquée dans les appels d’outils. Les identifiants du fournisseur sont stockés mais non injectés.',
    tellHermes: 'Indiquer le nom de la variable à Hermes'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `Enregistré sous ${stored}.`,
    valueIsolated: 'La valeur n’est pas ajoutée au chat ; utilisez {{secret:NAME}} dans les commandes. Elle est masquée dans la sortie des outils lorsqu’elle est suffisamment spécifique.',
    notPassthrough: 'Elle n’est pas transmise aux commandes en bac à sable.',
    redactedFalse: 'La sortie des outils ne masquera pas cette valeur.',
    indexedFalse: 'Une session ultérieure risque de ne pas pouvoir la masquer.'
  },
  modelNote: {
    prefix: (stored) =>
      `J’ai enregistré un secret dans la variable d’environnement ${stored}.`,
    passthrough: (stored) => `Utilisez {{secret:${stored}}} dans les commandes.`,
    sandbox: 'Les commandes en bac à sable ne la reçoivent pas.',
    username: (target) => `Le nom d'utilisateur est enregistré sous ${target} ; utilisez {{secret:${target}}}} pour l'utiliser.`,
    redactYes:
      'Ne me demandez pas de coller, afficher, copier ou encoder la valeur.',
    redactNo:
      'Ne me demandez pas de coller, afficher, copier ou encoder la valeur. La sortie des outils ne la nettoiera pas.'
  },
  palette: {
    open: 'Donner un secret à Hermes',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

const es = {
  dialog: {
    title: 'Dar un secreto a Hermes',
    description:
      'El valor se guarda en el host de la pasarela como variable de entorno. No se añade al chat; los comandos usan {{secret:NAME}} y la pasarela inserta el valor al ejecutarlos. La lectura directa del archivo de almacenamiento se bloquea en las llamadas de herramientas, y los valores suficientemente específicos se ocultan en la salida de las herramientas.'
  },
  labels: {
    variableName: 'Nombre de la variable',
    username: 'Nombre de usuario (opcional)',
    secret: 'Secreto',
    hint:
      'Los comandos usan {{secret:NAME}}; la pasarela sustituye el valor al ejecutarlos. La lectura directa del valor guardado se bloquea en las llamadas de herramientas. Las credenciales del proveedor se guardan pero no se inyectan.',
    tellHermes: 'Decir a Hermes el nombre de la variable'
  },
  placeholders: {
    variableName: 'DEPLOY_PASSWORD',
    username: 'deploy-bot',
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
    storedAs: (stored) => `Guardado como ${stored}.`,
    valueIsolated: 'El valor no se añade al chat; usa {{secret:NAME}} en los comandos. Se oculta en la salida de las herramientas cuando es suficientemente específico.',
    notPassthrough: 'No se reenvía a los comandos aislados.',
    redactedFalse: 'La salida de las herramientas no ocultará este valor.',
    indexedFalse: 'Una sesión posterior podría no poder ocultarlo.'
  },
  modelNote: {
    prefix: (stored) =>
      `He guardado un secreto en la variable de entorno ${stored}.`,
    passthrough: (stored) => `Usa {{secret:${stored}}} en los comandos.`,
    sandbox: 'Los comandos aislados no lo reciben.',
    username: (target) => `El nombre de usuario se guarda como ${target}; usa {{secret:${target}}}} para él.`,
    redactYes:
      'No me pidas pegar, imprimir, copiar ni codificar el valor.',
    redactNo:
      'No me pidas pegar, imprimir, copiar ni codificar el valor. La salida de las herramientas no lo limpiará.'
  },
  palette: {
    open: 'Dar un secreto a Hermes',
    keywords: ['password', 'token', 'secret', 'env']
  }
}

// ── Bundle-Export (plug-in-typisiert) ───────────────────────────────────────

const SECRET_DROP_LOCALES = {
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
  const parts = [t('success.storedAs', stored), t('success.valueIsolated')]

  if (result && result.injectable === false) {
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
  const injectable = !result || result.injectable !== false
  const redacted = !result || result.redacted !== false
  const use = injectable
    ? t('modelNote.passthrough', stored)
    : t('modelNote.sandbox')
  const redact = redacted
    ? t('modelNote.redactYes')
    : t('modelNote.redactNo')
  const account =
    result && result.username_stored_as
      ? ` ${t('modelNote.username', result.username_stored_as)}`
      : ''

  return `${t('modelNote.prefix', stored)} ${use} ${redact}${account}`
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
  const [username, setUsername] = useState('')
  const [tell, setTell] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const t = usePluginI18n('secret-drop')

  useEffect(() => {
    if (!open) {
      setValue('')
      setUsername('')
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
    const account = username.trim()

    setSubmitting(true)

    let result

    try {
      result = await rest('/drop', {
        method: 'POST',
        body: {
          name: secretName,
          value: secret,
          ...(account ? { username: account } : {})
        }
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
              t('labels.username'),
              jsx(Input, {
                autoComplete: 'off',
                disabled: submitting,
                onChange: event => setUsername(event.target.value),
                placeholder: t('placeholders.username'),
                spellCheck: false,
                value: username
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
  description: 'Store a secret on the gateway host and use it through an alias instead of pasting it into the chat',
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
        keywords: ['password', 'token', 'secret', 'env'],
        run: () => openDialog()
      }
    })
  }
}
