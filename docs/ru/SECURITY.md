# Безопасность и ответственность

В сервере есть встроенные защиты, чтобы снизить риск случайных разрушительных действий.

## Подтверждения (confirm)
- `delete_email`, `gmail_archive`, `calendar_create_meeting`,
  `drive_revoke_public` требуют `confirm=true`.
- `doc_fill_template` требует подтверждения, чтобы избежать массовой замены.

## Dry-run
- `batch_delete_emails` по умолчанию выполняется в dry-run.
- `sheet_find_replace` по умолчанию `dry_run=true`.
- `clear_range` автоматически требует подтверждения для больших диапазонов.

## Публичный доступ
- `share_file` запрещает `type=anyone` без `allow_public=true`.

## Профили инструментов (серверный allow-list)

Профиль убирает инструменты до того, как их увидит агент. Проверка идёт в двух
местах: `tools/list` возвращает только разрешённые инструменты, а `tools/call`
отклоняет всё, что вне профиля, с понятной ошибкой.

| Профиль | Инструментов | Для чего |
|---|---:|---|
| `full` | 89 | своя машина, полное доверие |
| `read-write` | 74 | ежедневная работа — деструктивные скрыты |
| `read-only` | 24 | разведка, демо, общие машины, недоверенные агенты |

```yaml
tool_profile: "read-only"
# Необязательные списки поверх профиля. Запрет важнее разрешения.
allowed_tools: ["workspace_search", "find_files", "read_sheet"]
denied_tools: ["gmail_search_and_summarize"]
```

Переменные окружения: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS="a,b"`, `MCP_DENIED_TOOLS="x,y"`.
У каждого ключа есть переменная окружения:

| Переменная | Переопределяет | Примечание |
|---|---|---|
| `MCP_CONFIG_FILE` | — | путь к `config.yaml` / `config.json` |
| `MCP_AUTH_TOKEN` | `mcp_auth_token` | обязателен до первого вызова инструмента |
| `MCP_TOOL_PROFILE` | `tool_profile` | `full` / `read-write` / `read-only` |
| `MCP_ALLOWED_TOOLS` | `allowed_tools` | белый список через запятую |
| `MCP_DENIED_TOOLS` | `denied_tools` | чёрный список; запрет сильнее разрешения |
| `MCP_DRY_RUN` | `dry_run` | `1` превращает записи в превью |
| `MCP_AUDIT_LOG` | `audit_log` | JSONL-журнал вызовов |
| `MCP_RETRY_ATTEMPTS` | `retry_attempts` | повторы на 429/5xx |
| `GOOGLE_CLIENT_SECRETS_FILE` | `client_secrets_file` | JSON OAuth-клиента |
| `GOOGLE_TOKEN_FILE` | `token_file` | кэш токена, перезаписывается при обновлении |
| `GOOGLE_BACKUP_DIR` | `backup_dir` | бэкапы Apps Script |
| `GOOGLE_LOG_FILE` | `log_file` | лог сервера |
| `GOOGLE_LOG_LEVEL` | `log_level` | `DEBUG` / `INFO` / `WARNING` |


Профили — это **дополнительный слой защиты, а не граница безопасности сама по себе**:
OAuth-токен всё равно несёт те скоупы, которые вы выдали. Самая надёжная комбинация —
read-only скоупы **и** профиль `read-only`: тогда ни токен, ни сервер не могут писать.

## MCP_AUTH_TOKEN
Все вызовы требуют, чтобы `MCP_AUTH_TOKEN` был сконфигурирован (переменная
окружения или `mcp_auth_token` в `config.yaml`). Это **проверка конфигурации
на стороне сервера**, которая гарантирует, что оператор осознанно включил
сервер. Она **не выполняет** аутентификацию клиента на уровне каждого запроса.

Проще всего думать о `MCP_AUTH_TOKEN` как о **локальном «ключе активации»
для этого MCP-сервера** — это дополнительная мера против случайного запуска
без настройки, а не защита от атак и не сетевая система аутентификации.

Для STDIO-серверов транспорт по своей природе локальный (IDE запускает процесс
напрямую), поэтому сетевая точка доступа для защиты отсутствует. Токен просто
предотвращает случайные запуски без осознанного шага настройки.

## Понимание OAuth Scopes

OAuth scopes определяют, к каким данным в вашем Google аккаунте получает доступ сервер. Вы можете настроить их в `config.yaml` в секции `scopes:`.

### Scopes по умолчанию (полный доступ)
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets"           # Чтение/запись таблиц
  - "https://www.googleapis.com/auth/drive"                   # Полный доступ к Drive
  - "https://www.googleapis.com/auth/documents"               # Чтение/запись документов
  - "https://www.googleapis.com/auth/gmail.modify"            # Чтение/отправка/удаление писем (включает чтение)
  - "https://www.googleapis.com/auth/calendar"                # Управление календарём
  - "https://www.googleapis.com/auth/script.projects"         # Доступ к Apps Script
  - "https://www.googleapis.com/auth/script.deployments"      # Деплои Apps Script
```

### Конфигурация только для чтения (безопаснее для тестирования)
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets.readonly"
  - "https://www.googleapis.com/auth/drive.readonly"
  - "https://www.googleapis.com/auth/documents.readonly"
  - "https://www.googleapis.com/auth/gmail.readonly"
  - "https://www.googleapis.com/auth/calendar.readonly"
```

### Минимальная конфигурация (только таблицы)
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets"
```

### Примеры для конкретных задач

**Сценарий 1: Email-ассистент (чтение + черновики)**
```yaml
scopes:
  - "https://www.googleapis.com/auth/gmail.readonly"
  - "https://www.googleapis.com/auth/gmail.compose"  # Только черновики, без отправки
```

**Сценарий 2: Автоматизация документов (Sheets + Docs)**
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets"
  - "https://www.googleapis.com/auth/documents"
```

**Сценарий 3: Организация файлов (только Drive)**
```yaml
scopes:
  - "https://www.googleapis.com/auth/drive.file"  # Только файлы, созданные этим приложением
```

### Изменение scopes
1. Отредактируйте `scopes:` в `config.yaml`
2. Удалите файл `token.json`
3. Перезапустите сервер — появится новое окно OAuth с обновлёнными разрешениями

## Рекомендации по настройке

### Для тестирования
- Создайте отдельный Google аккаунт для тестов
- Используйте scopes по умолчанию, чтобы протестировать все функции
- Храните тестовые данные отдельно от личных/рабочих

### Для постоянного использования
- Используйте минимальные scopes для вашей задачи
- Изучите список scopes выше и уберите ненужные API
- Сначала протестируйте с read-only scopes, затем добавьте права на запись

### Для рабочих/корпоративных аккаунтов
- Проверьте политики безопасности вашей организации перед подключением
- Рассмотрите использование служебного аккаунта с ограниченными правами
- Ведите логи операций для аудита
- Изучите [документацию Google Workspace Admin по scopes](https://developers.google.com/identity/protocols/oauth2/scopes)

## Доступ AI агента

**Важно:** Ваш AI агент (MCP клиент) получит доступ ко всем данным, разрешённым OAuth scopes. `MCP_AUTH_TOKEN` — это проверка конфигурации, а не механизм клиентской аутентификации; он не ограничивает самого AI агента.

Если вы беспокоитесь о случайных действиях:
- Начните с read-only scopes
- Используйте встроенные подтверждения (`confirm=True`, `dry_run=False`)
- Протестируйте на отдельном Google аккаунте
- Следите за логами сервера (`log_file` в конфиге)

## Уведомление об ответственности
Пользователь несёт ответственность за понимание рисков и последствий
операций, выполняемых этим сервером. Используйте его на свой риск и
в соответствии с политиками безопасности вашей организации.

Для вопросов о конкретных scopes см. [документацию Google OAuth 2.0 Scopes](https://developers.google.com/identity/protocols/oauth2/scopes).

## Выполнение кода и локальные файлы (v1.2)

- `script_run_function` выполняет произвольный код Apps Script с правами OAuth-токена.
  Помечен `destructiveHint`, поэтому профиль `read-write` его скрывает; `full` — открывает.
- `drive_download` и `drive_export` пишут на диск машины, где запущен сервер: `save_to`
  используется буквально, абсолютный путь возвращается в ответе. Без `overwrite=true`
  существующий файл не перезаписывается.
- `drive_upload` читает любой локальный файл, доступный процессу (лимит 100 МБ):
  считайте, что у процесса права его пользователя.

## HTTP-транспорт (v1.9)

- По умолчанию привязка к `127.0.0.1`. Не-loopback адрес требует `--allow-network`
  **и** `--insecure`; второй флаг подтверждает отсутствие TLS.
- Каждый запрос обязан прислать `Authorization: Bearer <token>`; сравнение
  постоянное по времени. Токены берутся из `http_tokens` (имя → токен) или из
  `mcp_auth_token` как `default`.
- Защита от DNS-rebinding отклоняет неожиданные `Host` и любые браузерные
  `Origin`, кроме явно разрешённых.
- `GET /healthz` публичный по замыслу и не отдаёт данных.
- Аудит-лог пишет имя токена в поле `client`, поэтому общий деплой можно разложить
  по конкретным токенам.
- Выход в сеть означает, что все пользуются одной Google-личностью. Для настоящего
  multi-user нужен TLS-прокси, отдельный service account, минимальные скоупы и
  отдельный токен каждому клиенту.
