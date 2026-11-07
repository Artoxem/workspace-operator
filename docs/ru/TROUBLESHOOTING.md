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
| `config file not found` | `MCP_CONFIG_FILE` указывает в никуда | дать абсолютный путь; можно работать только на переменных окружения |

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

## HTTP-транспорт

| Симптом | Причина | Что делать |
|---|---|---|
| `401 Unauthorized` | нет или неверный bearer | отправить `Authorization: Bearer <MCP_AUTH_TOKEN>`, сверить с конфигом |
| `421 Misdirected Request` | недопустимый `Host` (обычно remapped порт контейнера) | обновиться до 1.13.1+ или передать `--allow-host 127.0.0.1:8791` |
| `403 Forbidden` от Google | квота или выключенный API | см. раздел про Google выше |
| `address already in use` | порт занят | `--port 8790` |
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
| сервер стартует, инструменты отдают 401 | `MCP_AUTH_TOKEN` не передан | `-e MCP_AUTH_TOKEN=...` |
| правки конфига игнорируются | файл запечён в образ | смонтировать `config.docker.yaml` поверх `/app/config.yaml` |

Минимальная рабочая команда:

```bash
docker run --rm -p 127.0.0.1:8765:8765 \
  -v "$HOME/.google:/home/app/.google" \
  -v "$PWD/config.docker.yaml:/app/config.yaml:ro" \
  -e MCP_AUTH_TOKEN="change_me" \
  ghcr.io/artoxem/workspace-operator:latest
```

## Инструменты и данные

| Симптом | Причина | Что делать |
|---|---|---|
| `Unknown tool: …` | профиль или allow/deny скрывает инструмент | `workspace-operator tools --profile full`; проверить `MCP_DENIED_TOOLS` |
| `CONFIRMATION REQUIRED` | разрушительный инструмент вызван один раз | повторить вызов с `confirm=true`, посмотрев превью |
| инструмент возвращает превью вместо действия | включён dry-run | убрать `MCP_DRY_RUN` / `dry_run: false` |
| `403 quota exceeded`, `rateLimitExceeded` | лимиты Google | подождать, поднять `MCP_RETRY_ATTEMPTS`, сузить диапазон |
| `File not found` | неверный ID или нет доступа у аккаунта | открыть файл в браузере под тем же аккаунтом |
| не скачивается Google Doc/Sheet/Slide | у нативных файлов нет бинарного содержимого | использовать `drive_export` (pdf/docx/xlsx/pptx/csv) |
| большой лист читается очень долго | запрос всего листа | передать диапазон (`A1:D100`) |
| `slides_replace_text` отказывается работать | операция разрушительная | добавить `confirm=true` |

## Логи и сообщение об ошибке

- `log_file` — обычный лог сервера; для деталей `GOOGLE_LOG_LEVEL=DEBUG`.
- `MCP_AUDIT_LOG` — строка JSON на вызов: инструмент, профиль, статус, длительность,
  **имена** аргументов (значения не пишутся).
- Вывод `workspace-operator doctor` можно показывать: там пути и скоупы, но не секреты.

В отчёт стоит включить: версию (`workspace-operator version`), команду запуска, имя
инструмента с аргументами (без секретов) и последние строки лога.
