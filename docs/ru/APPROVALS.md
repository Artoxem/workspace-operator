# Подтверждение destructive-действий человеком

Workspace Operator оставляет destructive-инструменты агенту, но сервер не
выполняет их без подтверждения человека.

Это серверный шлюз, а не просьба в промпте: агент может попросить удалить, но
не может сам подтвердить запрос.

## Как это работает

1. Агент вызывает destructive-инструмент:

   ```json
   {"name": "drive_trash", "arguments": {"file_id": "..."}}
   ```

2. Если клиент поддерживает MCP elicitation, сервер спрашивает пользователя
прямо в чате: **Подтвердить действие?** Accept выполняет его один раз, decline
отменяет.

   Если клиент не поддерживает elicitation, сервер **ничего не меняет** и
   возвращает обычный результат с `approval_id`:

   ```text
   ⚠️ APPROVAL REQUIRED — the action has NOT run.
   {"status": "approval_required", "approval_id": "apr_…", ...}
   ```

3. В fallback-сценарии агент показывает `approval_id` пользователю, и тот подтверждает локально:

   ```bash
   workspace-operator approvals list
   workspace-operator approvals show apr_…
   workspace-operator approvals approve apr_…
   # или отклонить
   workspace-operator approvals deny apr_…
   ```

4. Агент повторяет **тот же** вызов с `approval_id`:

   ```json
   {"name": "drive_trash", "arguments": {
     "file_id": "...",
     "approval_id": "apr_…"
   }}
   ```

5. Сервер проверяет и расходует approval, затем выполняет действие один раз.

Успех, pending, deny, expiry, повторное использование и несовпадение аргументов
возвращаются как обычные tool-результаты с инструкцией. MCP-сессия не падает.
In-chat elicitation — основной путь; CLI используется только как fallback для
клиентов без поддержки elicitation.

## Привязка и срок

Approval привязан к:

- имени инструмента;
- `action` для консолидированных инструментов;
- SHA-256 хешу всех аргументов, кроме `approval_id` и `confirm`;
- времени истечения (по умолчанию 15 минут, `approval_ttl`).

Изменение `file_id`, `plan_id`, диапазона или любого другого аргумента
аннулирует approval. Он одноразовый: после выполнения id нельзя использовать
снова.

`confirm=true` остаётся флагом намерения, но сам по себе не достаточен:
действие освобождает именно подтверждение человека.

## CLI

```bash
workspace-operator approvals list          # ожидающие запросы
workspace-operator approvals show apr_…    # детали запроса
workspace-operator approvals approve apr_… # разрешить конкретный вызов
workspace-operator approvals deny apr_…    # заблокировать
```

CLI читает ту же конфигурацию, что и сервер. В Docker каталог подтверждений
смонтирован вместе с data:

```bash
# на хосте, рядом с docker-compose.yml
MCP_APPROVAL_DIR=./data/approvals workspace-operator approvals list
```

Или внутри контейнера:

```bash
docker compose exec workspace-operator workspace-operator approvals list
```

## Конфигурация

```yaml
approval_dir: "data/approvals"  # в контейнере: /home/app/data/approvals
approval_ttl: 900               # секунды
```

Переменные: `MCP_APPROVAL_DIR`, `MCP_APPROVAL_TTL`.

## Что требует подтверждения

`confirm=true` + approval человека применяются к:

`drive_trash`, `drive_permissions`, `docs_edit`, `sheets_delete`,
`gmail_delete`, `calendar_delete`, `script_run`, `bulk_run`, `bulk_undo`.

Чтение, обычная запись, черновики и `dry_run` не требуют approval.
`bulk_plan` всегда dry-run; подтверждение запрашивается при `bulk_run`.

## Модель угроз

Approval защищает от самостоятельных действий агента через MCP. Он не защищает
от агента с произвольным локальным shell вне MCP и от человека, который
подтверждает запрос не читая summary. Держите каталог approvals локальным,
запускайте CLI от того же пользователя, что и сервер, и не открывайте MCP
эндпоинт недоверенным пользователям.
