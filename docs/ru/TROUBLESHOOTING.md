# Если что-то не работает

Начните со встроенной проверки — она закрывает большинство случаев:

```bash
workspace-operator doctor            # конфиг, токен, скоупы, доступность API
workspace-operator doctor --offline  # то же, но без обновления токена и сети
```

`doctor` показывает, что настроено, чего не хватает и какой API отвечает. Если он
зелёный, а проблема осталась, таблицы ниже идут снаружи внутрь: установка → OAuth →
транспорт → Docker → инструменты.

## Установка и запуск

| Симптом | Причина | Что делать |
|---|---|---|
| `ModuleNotFoundError: No module named 'workspace_operator'` | другой интерпретатор или venv | поставить в то же окружение: `pip install workspace-operator-mcp`, либо запускать `python server.py` из репозитория |
| `package requires Python >=3.10` | старый Python | обновить интерпретатор или указать новый в конфиге клиента |
| `python: command not found` (Windows) | Python не в `PATH` | использовать `py -3.12` или полный путь к `python.exe` |
| сервер сразу завершается, в консоли пусто | stdout занят протоколом, логи в файле | открыть `log_file` (по умолчанию `~/.google/mcp_operations.log`) |
| `Config file not found` | `--config` или `MCP_CONFIG_FILE` указывает на несуществующий файл; сервер завершается, а не переходит молча на умолчания | исправить путь либо убрать его и дать поиску найти `./config.yaml` или файл пользователя; `workspace-operator doctor` показывает, какой файл использован |

## Google OAuth

Полная настройка: [AUTH_SETUP.md](AUTH_SETUP.md).

| Симптом | Причина | Что делать |
|---|---|---|
| `invalid_grant`, `Token has been expired or revoked` | токен отозван, истёк или изменились скоупы | удалить `token.json`, авторизоваться заново |
| `access_denied`, `insufficientPermissions` | API не включён или скоуп добавлен позже | включить API, удалить `token.json`, войти заново |
| `redirect_uri_mismatch` | OAuth-клиент не Desktop app | создать новый Client ID типа **Desktop app** |
| `This app isn't verified` | consent screen в режиме тестирования | Advanced → **Go to app (unsafe)**, либо опубликовать приложение |
| `403: <API> has not been used in project …` | API выключен | включить в Cloud Console, подождать минуту, повторить |
| `FileNotFoundError: oauth.keys.json` | неверный `client_secrets_file` | поправить путь в `config.yaml` или `GOOGLE_CLIENT_SECRETS_FILE` |
| браузер не открывается | headless/удалённая сессия | скопировать напечатанный URL в браузер, код вставить обратно |
| проверки проходят, инструмент отдаёт `404` | файл у другого аккаунта или неверный ID | проверить ID и доступ у аккаунта |
| `doctor`: `[FAIL] stray secret files` | рядом с токеном остались `token.json.bak-*`, `service-account.json` или `credentials.json` | отозвать приложение в аккаунте Google, затем удалить файлы |
| `doctor`: `[FAIL] secret file permissions` | секреты доступны другим пользователям | оставить права только вам (`chmod 600` / ACL только владельца); `token.json` создаётся именно так |
| `403: Request had insufficient authentication scopes` | токен выдан до добавления скоупа (фильтрам нужен `gmail.settings.basic`) | удалить `token.json` и авторизоваться заново; `doctor` покажет `[FAIL] scopes` и код 1 |

## HTTP-транспорт

| Симптом | Причина | Что делать |
|---|---|---|
| `401 Unauthorized` | нет или неверный bearer | отправить `Authorization: Bearer <MCP_AUTH_TOKEN>`, сверить с конфигом |
| `421 Misdirected Request` | недопустимый `Host` (обычно remapped порт контейнера) | обновиться до 1.13.1+ или передать `--allow-host 127.0.0.1:8791` |
| `403 Forbidden` от Google | квота или выключенный API | см. раздел про Google выше |
| `address already in use` | порт занят | `--port 8790` |
| отказ: *token 'default' is a placeholder value* / *shorter than 24 characters* | bearer для HTTP слишком простой | сгенерировать: `python -c "import secrets; print(secrets.token_urlsafe(32))"` и задать `MCP_AUTH_TOKEN` |
| страница одобрения пишет *invalid or expired link* / `403` на Approve | в ссылке нет секрета или POST пришёл с другого origin | получить ссылку командой `workspace-operator approvals link <id>`; открывать напрямую, не через прокси, меняющий `Host`/`Origin` |
| при destructive-вызове не открывается вкладка браузера | не запущен `approvals watch`, `MCP_APPROVAL_BROWSER_WAIT` равен `0`, или помощник смотрит другую очередь | запустить `workspace-operator approvals watch` на машине с доступом к той же очереди и задать `MCP_APPROVAL_BROWSER_WAIT`; до этого вызов вернёт `approval_id`, и решение принимается через `approvals approve` или `approvals link` |
| отказ: *non-loopback binding requires `--allow-network`* | сетевой bind без подтверждения | добавить **оба** флага `--allow-network` и `--insecure`, впереди поставить TLS-прокси |
| `Empty reply from server` | неверный путь или метод | `POST /mcp`, а не `/`; `GET /healthz` — единственный GET |
| CORS-ошибка в браузере | origin запрещены намеренно | использовать нативный MCP-клиент, а не веб-страницу |

Проверка вручную:

```bash
curl http://127.0.0.1:8765/healthz

curl -s http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Docker

| Симптом | Причина | Что делать |
|---|---|---|
| `Permission denied` на `~/.google` (Linux) | контейнер работает под uid 10001 | `chmod -R a+r ~/.google` либо запуск с `--user $(id -u):$(id -g)` |
| обновление токена не проходит, файл только для чтения | монтирование `:ro` | монтировать креденшелы **на запись**: сервер перезаписывает токен |
| ошибки с путями `C:\…` | Windows-конфиг внутри Linux | монтировать `config.docker.yaml` — там пути `/home/app/...` |
| контейнер `(unhealthy)` | неверный токен, нет конфига или падение | `docker logs <container>`, проверить `MCP_AUTH_TOKEN` и пути монтирования |
| `421` на remapped порту | защита от DNS-rebinding (исправлено в 1.13.1) | взять `:latest` или добавить `--allow-host` |
| `exec format error` | архитектура образа не совпадает | образ есть для `amd64` и `arm64`; перекачать на поддерживаемом хосте |
| порт опубликован, но ответа нет | образ по умолчанию слушает `127.0.0.1` внутри контейнера | добавить `--http --host 0.0.0.0 --allow-network --insecure` (Compose уже добавляет) и оставить `-p 127.0.0.1:…` |
| `Error: … protected location … cannot be uploaded` | `drive_write(action="upload")` отклоняет секреты, одобрения, логи и всё вне `upload_roots` | загрузить копию из разрешённой папки; проверить `MCP_UPLOAD_ROOTS` |
| сервер стартует, инструменты отдают 401 | `MCP_AUTH_TOKEN` не передан | `-e MCP_AUTH_TOKEN=...` |
| правки конфига игнорируются | файл запечён в образ | смонтировать `config.docker.yaml` поверх `/app/config.yaml` |

Минимальная рабочая команда:

```bash
docker run --rm -p 127.0.0.1:8765:8765 \
  -v "$HOME/.google:/home/app/.google" \
  -v "$PWD/config.docker.yaml:/app/config.yaml:ro" \
  -e MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  ghcr.io/artoxem/workspace-operator:latest \
  --http --host 0.0.0.0 --port 8765 --allow-network --insecure
```

Образ по умолчанию слушает `127.0.0.1`, поэтому без флагов в конце команды
опубликованный порт ничего не отвечает. Оставьте префикс `127.0.0.1:` в `-p`:
эндпоинт без TLS.

## Инструменты и данные

| Симптом | Причина | Что делать |
|---|---|---|
| `Unknown tool: …` | профиль или allow/deny скрывает инструмент | `workspace-operator tools --profile full`; проверить `MCP_DENIED_TOOLS` |
| `Operation op_… not found or expired` | подготовленная операция Apps Script уже выполнена, отменена или старше `operation_ttl` | повторите шаг подготовки; что ожидает — видно в `data/operations/` |
| `CONFIRMATION REQUIRED` | разрушительный инструмент вызван один раз | повторить вызов с `confirm=true`, посмотрев превью |
| инструмент возвращает превью вместо действия | включён dry-run | убрать `MCP_DRY_RUN` / `dry_run: false` |
| `403 quota exceeded`, `rateLimitExceeded` | лимиты Google | подождать, поднять `MCP_RETRY_ATTEMPTS`, сузить диапазон |
| `File not found` | неверный ID или нет доступа у аккаунта | открыть файл в браузере под тем же аккаунтом |
| не скачивается Google Doc/Sheet | у нативных файлов нет бинарного содержимого | использовать `drive_read(action="export")` (pdf/docx/xlsx/csv) |
| большой лист читается очень долго | запрос всего листа | передать диапазон (`A1:D100`) |
| Удалённый инструмент 1.x отвечает `unknown tool` | в 2.0 консолидированные инструменты | используйте новое имя/action из `docs/MIGRATION_2.0.md` |

## Логи и сообщение об ошибке

- `log_file` — обычный лог сервера; для деталей `GOOGLE_LOG_LEVEL=DEBUG`.
- `MCP_AUDIT_LOG` — строка JSON на вызов: инструмент, профиль, статус, длительность,
  **имена** аргументов (значения не пишутся).
- Вывод `workspace-operator doctor` можно показывать: там пути и скоупы, но не секреты.

В отчёт стоит включить: версию (`workspace-operator version`), команду запуска, имя
инструмента с аргументами (без секретов) и последние строки лога.
