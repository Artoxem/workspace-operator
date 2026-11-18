# Безопасность и ответственность

В сервере есть встроенные защиты, чтобы снизить риск случайных разрушительных действий.

## Подтверждения и approval человека
- Destructive-вызовы сначала возвращают `APPROVAL_REQUIRED`; человек выполняет `workspace-operator approvals approve <id>` (или открывает страницу по ссылке из `workspace-operator approvals link <id>`), агент повторяет вызов с одноразовым `approval_id`.
- Агент никогда не получает ссылку для браузера: в ней секрет конкретного одобрения, который читает только канал человека (CLI). См. [APPROVALS.md](APPROVALS.md).
- Approval привязан к хешу tool/action/аргументов, истекает по `approval_ttl` и используется один раз.
- `drive_trash`, `drive_permissions`, `docs_edit`, `sheets_delete`,
  `gmail_delete`, `calendar_delete`, `script_run`, `bulk_run` и `bulk_undo`
  требуют `confirm=true`.
- Router проверяет это до handler; в handler остаётся вторая проверка.

## Dry-run и предпросмотр
- `bulk_plan` всегда dry-run.
- `sheets_write` → `find_replace` возвращает предпросмотр без `confirm=true`.
- `gmail_settings` → `label_apply` по умолчанию `dry_run=true`.

## Без безвозвратного удаления файлов
- `drive_trash` только перемещает файл в корзину; `drive_empty_trash` и передачи
  владения нет.
- Удаление Gmail перемещает письма в корзину.

## Публичный доступ
- Публичный шаринг выключен по умолчанию. `drive_write` → `share` требует
  `allow_public_sharing=true` в конфиге **и** `allow_public=true`.

## Профили инструментов (серверный allow-list)

Профиль убирает инструменты до того, как их увидит агент. Проверка идёт в двух
местах: `tools/list` возвращает только разрешённые инструменты, а `tools/call`
отклоняет всё, что вне профиля, с понятной ошибкой.

| Профиль | Инструментов | Для чего |
|---|---:|---|
| `core` | 20 | ежедневное чтение/запись без форматирования и destructive |
| `full` | 39 | форматирование, destructive, Forms, Postmaster, Script |
| `read-write` | 30 | автоматизация без destructive |
| `read-only` | 17 | разведка, демо, общие машины, недоверенные агенты |

```yaml
tool_profile: "read-only"
# Необязательные списки поверх профиля. Запрет важнее разрешения.
allowed_tools: ["workspace_search", "sheets_read", "gmail_read"]
denied_tools: ["gmail_write", "drive_write"]
```

Переменные окружения: `MCP_TOOL_PROFILE`, `MCP_ALLOWED_TOOLS="a,b"`, `MCP_DENIED_TOOLS="x,y"`.
У каждого ключа есть переменная окружения:

| Переменная | Переопределяет | Примечание |
|---|---|---|
| `MCP_CONFIG_FILE` | — | путь к `config.yaml` / `config.json` |
| `MCP_AUTH_TOKEN` | `mcp_auth_token` | обязателен до первого вызова инструмента |
| `MCP_TOOL_PROFILE` | `tool_profile` | `core` / `full` / `read-write` / `read-only` |
| `MCP_APPROVAL_DIR` | `approval_dir` | очередь одобрений человеком; монтируйте с правом записи |
| `MCP_APPROVAL_TTL` | `approval_ttl` | время жизни одобрения в секундах |
| `MCP_APPROVAL_URL` | `approval_url` | базовый URL браузерной страницы одобрений |
| `MCP_OPERATION_DIR` | `operation_dir` | подготовленные операции Apps Script (по умолчанию `data/operations`) |
| `MCP_OPERATION_TTL` | `operation_ttl` | сколько секунд подготовленная операция остаётся выполнимой (по умолчанию 600) |
| `MCP_UPLOAD_ROOTS` | `upload_roots` | папки через запятую, из которых `drive_write(action="upload")` может читать; пусто = любая папка, кроме секретов |
| `MCP_SCOPE_ROUTING` | `scope_routing` | скрывать инструменты без нужного Google-скоупа |
| `MCP_ALLOW_PUBLIC_SHARING` | `allow_public_sharing` | разрешить публичные ссылки (по умолчанию выкл.) |
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

## Модели развёртывания и изоляция

Workspace Operator — **однопользовательский сервер**. Один процесс использует
один OAuth-токен и один профиль инструментов. Несколько MCP-клиентов могут
подключиться, но это клиенты одного пользователя, а не разные пользователи.

| Модель | Поддерживается | Замечания |
|---|---|---|
| Один человек, несколько клиентов | Да | `http_tokens` даёт каждому клиенту имя для аудит-лога; аккаунт и профиль общие |
| Команда на одном Google-аккаунте | Да, без изоляции | Один Drive/Gmail, общий аудит и массовые задачи; для недоверенных — `read-only` |
| Несколько Google-аккаунтов | Нет, по экземпляру на аккаунт | Каждому: свой `config.yaml`, `token.json`, `data/` и порт |
| Публичный или multi-tenant сервис | Нет | Нет пользователей, квот, профилей на пользователя и владельцев задач |

### Что делает bearer-токен, а что нет

- Аутентифицирует запрос к этому экземпляру и даёт токену имя в аудит-логе
  (поле `client`).
- **Не** ограничивает инструменты, данные и задачи. Любой токен видит все
  доступные инструменты и может вызвать `bulk_status`, `bulk_cancel` или
  `bulk_result` для любой задачи.
- `http_tokens` — реестр клиентов, не пользователей. Ролей нет: профиль и
  allow/deny-списки глобальные.

### Рекомендуемые схемы

**Один человек, один или несколько клиентов.** stdio для одного настольного
клиента или один HTTP-контейнер с отдельным токеном на клиента. Порт — только
на loopback.

**Небольшая команда на одном аккаунте.** Работает, но считайте всех одним
пользователем. Для тех, кому нужно только смотреть, ставьте профиль
`read-only`, не делитесь `MCP_AUTH_TOKEN` и помните, что аудит общий.

**Несколько аккаунтов.** По экземпляру на аккаунт:

```bash
docker run -d --name workspace-alice \
  -p 127.0.0.1:8765:8765 \
  -v /home/alice/.google:/home/app/.google \
  -v /home/alice/workspace-data:/home/app/data \
  -e MCP_AUTH_TOKEN=... \
  ghcr.io/artoxem/workspace-operator:latest
```

Повторите с другим портом, конфигом и папкой Google для каждого человека.
Reverse proxy может маршрутизировать по домену или пути. Это единственная
конфигурация с реальной изоляцией данных; горизонтально масштабировать один
токен на несколько экземпляров нельзя — планы и задачи лежат на локальном диске.

### Если нужна многопользовательскость

Сегодня это вне рамок. Настоящему multi-tenant сервису нужны OAuth на
пользователя, маппинг токен→пользователь, профили и квоты на пользователя,
владельцы задач и общее хранилище задач. Ничего этого в сервере нет.

## MCP_AUTH_TOKEN
Все вызовы требуют, чтобы `MCP_AUTH_TOKEN` был сконфигурирован (переменная
окружения или `mcp_auth_token` в `config.yaml`). Это **проверка конфигурации
на стороне сервера**, которая гарантирует, что оператор осознанно включил
сервер. Она **не выполняет** аутентификацию клиента на уровне каждого запроса.

По **stdio** `MCP_AUTH_TOKEN` — это **локальный «ключ активации»**: транспорт по
своей природе локальный (IDE запускает процесс напрямую), и токен лишь
предотвращает случайные запуски без осознанного шага настройки.

По **HTTP** это же значение (или персональные `http_tokens`) — настоящий
bearer-токен `Authorization: Bearer` для каждого запроса, поэтому он должен быть
случайным и секретным: сервер не запустится с заглушкой (`change_me`, …) или
токеном короче 24 символов.

Где его хранить:

- Предпочитайте переменную окружения `MCP_AUTH_TOKEN` (или менеджер секретов), а не
  `mcp_auth_token` в `config.yaml`; `workspace-operator doctor` предупредит, если
  токен лежит в конфиге.
- Генерация: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- Смена токена не требует новой авторизации в Google.

## Секреты на диске

| Файл | Что даёт | Как обрабатывается |
|---|---|---|
| `token.json` | доступ к вашему Google-аккаунту в пределах выданных скоупов | пишется атомарно под файловой блокировкой, права только у владельца (`0600`, ACL только владельца в Windows) |
| `oauth.keys.json` | личность OAuth-клиента (client secret) | храните вне репозитория, права только у владельца |
| `data/approvals/*.json` | одноразовые секреты одобрений | создаются с правами владельца; агенту не возвращаются |
| `data/operations/*.json` | исходники Apps Script, подготовленные к записи | права владельца; истекают по `operation_ttl`; удаляются при выполнении |
| `.env` | `MCP_AUTH_TOKEN` для Docker Compose | в `.gitignore`; права только у владельца |

`workspace-operator doctor` проверяет, что секретные файлы недоступны другим
пользователям, и находит остатки рядом с токеном (старые `token.json.bak-*`,
`service-account.json`, `credentials.json`). Удаляйте неиспользуемые учётные
данные: бэкап токена остаётся рабочим ключом, пока его не отозвали.

**Если секрет мог утечь:** отзовите доступ приложения на
<https://myaccount.google.com/permissions> (это сразу обнуляет все копии
refresh-токена), удалите ключ сервисного аккаунта в Cloud, если он был, удалите
`token.json` и бэкапы, сгенерируйте новый `MCP_AUTH_TOKEN` и запустите
`workspace-operator doctor`, чтобы авторизоваться заново.

`drive_write(action="upload")`, локальный экспорт и одобрения используют один
список защищённых путей (`secure_files.protected_paths`), поэтому агент не сможет
с их помощью перемещать ваши учётные данные.

## Понимание OAuth Scopes

OAuth scopes определяют, к каким данным в вашем Google аккаунте получает доступ сервер. Вы можете настроить их в `config.yaml` в секции `scopes:`.

### Scopes по умолчанию (полный доступ)
```yaml
scopes:
  - "https://www.googleapis.com/auth/spreadsheets"
  - "https://www.googleapis.com/auth/drive"
  - "https://www.googleapis.com/auth/script.projects"
  - "https://www.googleapis.com/auth/script.deployments"
  - "https://www.googleapis.com/auth/documents"
  - "https://www.googleapis.com/auth/gmail.modify"
  - "https://www.googleapis.com/auth/gmail.settings.basic"
  - "https://www.googleapis.com/auth/calendar"
  - "https://www.googleapis.com/auth/tasks"
  - "https://www.googleapis.com/auth/forms.body"
  - "https://www.googleapis.com/auth/forms.responses.readonly"
  - "https://www.googleapis.com/auth/postmaster.domain"
  - "https://www.googleapis.com/auth/postmaster.traffic.readonly"
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

- `script_run` выполняет произвольный код Apps Script с правами OAuth-токена.
  Помечен `destructiveHint`, поэтому профиль `read-write` его скрывает; `full` — открывает.
- `drive_read(action="export")` пишет на диск машины, где запущен сервер: `save_to`
  используется буквально, абсолютный путь возвращается в ответе. Без `overwrite=true`
  существующий файл не перезаписывается.
- `drive_write(action="upload")` читает локальные файлы (лимит 100 МБ). Секреты OAuth
  отклоняются всегда: настроенные пути токена, client secrets и бэкапов, `~/.google`,
  `~/.ssh`, `~/.aws`, `~/.gnupg`, каталоги одобрений, bulk и логов, а также файлы
  `token.json`, `.env*`, `oauth.keys.json`, `*.pem`, `*.key` и подобные. Задайте
  `upload_roots` (`MCP_UPLOAD_ROOTS`), чтобы ограничить загрузку выбранными папками; в
  Docker-конфиге по умолчанию `/home/app/data/upload`. Без `upload_roots` у процесса
  остаются права его пользователя на остальные файлы.
- Имена из удалённых данных (вложения писем, названия в Drive) перед сохранением
  сводятся к имени файла (`../`, буквы дисков, служебные имена Windows и недопустимые
  символы удаляются), поэтому вредоносное вложение не запишет файл за пределы целевой
  папки. Явный путь файла в `save_to`, заданный вызывающим, по-прежнему
  учитывается.

## HTTP-транспорт (v1.9)

- По умолчанию привязка к `127.0.0.1`. Не-loopback адрес требует `--allow-network`
  **и** `--insecure`; второй флаг подтверждает отсутствие TLS.
- Каждый запрос обязан прислать `Authorization: Bearer <token>`; сравнение
  постоянное по времени. Токены берутся из `http_tokens` (имя → токен) или из
  `mcp_auth_token` как `default`.
- Защита от DNS-rebinding отклоняет неожиданные `Host` и любые браузерные
  `Origin`, кроме явно разрешённых.
- `GET /healthz` публичный по замыслу и не отдаёт данных.
- Сервер не запустится по HTTP с токеном-заглушкой (`change_me`, …) или короче 24
  символов. Сгенерируйте токен командой
  `python -c "import secrets; print(secrets.token_urlsafe(32))"` и не храните его в
  `config.yaml`: используйте переменную окружения `MCP_AUTH_TOKEN`.
- Браузерные страницы одобрений защищены секретом конкретного одобрения, проверкой
  `Origin`/`Host` и строгими заголовками ответа; см. `APPROVALS.md`.
- Docker-образ по умолчанию слушает `127.0.0.1`. `docker-compose.yml` передаёт
  `--allow-network --insecure` вместе с публикацией порта только на loopback; при
  обычном `docker run` привязку к сети нужно включать явно.
- Аудит-лог пишет имя токена в поле `client`, поэтому общий деплой можно разложить
  по конкретным токенам.
- Выход в сеть означает, что все пользуются одной Google-личностью. Для настоящего
  multi-user нужен TLS-прокси, отдельный service account, минимальные скоупы и
  отдельный токен каждому клиенту.
