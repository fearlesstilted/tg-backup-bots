# tg_backup_bots

MVP двух Telegram backup-ботов для ShmaliShop:

- **Reviews bot** — сегменты `ru_reviews`, `foreign_reviews`.
- **Private bot** — сегменты `ru_private`, `foreign_private`.

Стек: Python, aiogram 3, SQLite. Один процесс запускает оба бота.

## Интеграция с сайтом

Фронтенд ShmaliShop читает deep-link ссылки ботов из Supabase `site_settings`.
Для подключения не нужно менять фронтенд-код, достаточно заполнить значения в
админке или SQL:

- [INTEGRATION.md](INTEGRATION.md)
- [integration/site_settings_upsert.sql](integration/site_settings_upsert.sql)

## Установка

Нужен Python 3.11+.

```bash
cd tg_backup_bots
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
$EDITOR .env
```

`.env` лежит в `.gitignore`. Нельзя коммитить bot tokens, приватные ссылки,
SQLite базу и backup-файлы.

## Запуск

```bash
python -m app.main
```

## Переменные окружения

| Переменная | Зачем нужна |
| --- | --- |
| `REVIEWS_BOT_TOKEN` | token бота отзывов |
| `PRIVATE_BOT_TOKEN` | token приватного бота |
| `ADMIN_IDS` | Telegram ID админов через запятую |
| `DATABASE_PATH` | путь к SQLite базе, по умолчанию `./bots.db` |
| `PRIVATE_REQUIRE_ACCESS_TOKEN` | если `true`, private bot принимает только подписанные short tokens |
| `PRIVATE_ACCESS_SECRET` | HMAC secret для проверки private access token |
| `RU_REVIEWS_LINK` / `FOREIGN_REVIEWS_LINK` | ссылки, которые выдаёт reviews bot после opt-in |
| `RU_PRIVATE_LINK` / `FOREIGN_PRIVATE_LINK` | ссылки, которые выдаёт private bot после opt-in |

## Пользовательский flow

Пользователь открывает ссылку вида:

```text
https://t.me/<bot_username>?start=<segment>
```

Бот сохраняет пользователя, показывает кнопку подтверждения и после нажатия
выдаёт нужную ссылку.

Разрешённые сегменты:

- reviews bot: `ru_reviews`, `foreign_reviews`, `test`
- private bot: `ru_private`, `foreign_private`, `test`

Если сегмент неправильный или ссылка открыта без параметра, пользователь
попадает в `unknown` и ссылку не получает.

Для production private-доступа нужно включить:

```text
PRIVATE_REQUIRE_ACCESS_TOKEN=true
```

Тогда private bot не принимает публичные `?start=ru_private` /
`?start=foreign_private`, а ждёт короткий подписанный token от сайта.
Token должен генерироваться только на сервере после проверки оплаченного заказа.

Для ручного smoke-теста token можно сгенерировать локально:

```bash
PRIVATE_ACCESS_SECRET=... .venv/bin/python -m app.access_tokens ru_private 600
```

## Админ-команды

Доступны только Telegram ID из `ADMIN_IDS`:

- `/menu` — показать кнопочное меню.
- `/stats` — статистика по сегментам.
- `/broadcast <segment>` — начать рассылку.
- `/broadcast_status <id>` — статус рассылки.
- `/stop_broadcast <id>` — остановить активную рассылку.
- `/last` — последние 10 рассылок.
- `/test <segment>` — отправить следующий текст только себе.

У админа также есть кнопки:

- `📊 Статистика`
- `📜 Последние`
- `📣 Рассылка RU`
- `📣 Рассылка Foreign`
- `ℹ️ Помощь`

Обычный пользователь не видит админ-функции. Его доступ: `/start`, кнопка
подтверждения и `/stop`.

## Движок рассылок

- Отправка идёт последовательно, не через `gather`.
- Цель: примерно 18 сообщений/сек.
- `TelegramRetryAfter` — ждём и повторяем отправку тому же пользователю.
- `TelegramForbiddenError`, `chat not found`, `user is deactivated` — пользователь
  помечается inactive, счётчик `blocked`.
- Остальные ошибки — `failed`, пользователь остаётся active.
- Delivery logs и counters пишутся пачками по 50.
- Stop flag перечитывается из БД каждые 50 отправок.
- После рестарта зависшие `processing` рассылки переводятся в `interrupted`.

## Проверки

```bash
python3 -m compileall app tests
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m app.healthcheck
.venv/bin/python -m app.simulate_broadcast --db /tmp/tg_backup_sim.db --users 1000 --bot reviews --segment test
```

Через `make`:

```bash
make test
make check
make simulate
make health
```

## Live smoke test

Запускать только на тестовых аккаунтах и ботах.

1. Заполнить `.env`: два bot tokens, свой Telegram ID в `ADMIN_IDS`, четыре invite links.
2. Запустить `.venv/bin/python -m app.healthcheck`.
3. Запустить `python -m app.main`.
4. В Telegram открыть оба бота.

Проверить:

| Шаг | Действие | Ожидание |
| --- | --- | --- |
| 1 | `/start ru_reviews` в reviews bot | приветствие + кнопка `✅ Подтвердить` |
| 2 | нажать кнопку | бот выдаёт RU reviews invite link |
| 3 | `/start foreign_reviews` | приветствие EN + кнопка `✅ Confirm` |
| 4 | `/start garbage` | fallback без выдачи ссылки, сегмент `unknown` |
| 5 | `/stats` от админа | статистика по сегментам |
| 6 | `/test ru_reviews` | сообщение приходит только админу |
| 7 | `/broadcast ru_reviews` → текст → `Dry-run` | ничего не отправлено |
| 8 | `/broadcast ru_reviews` → текст → `Отправить` | создаётся рассылка, статус виден через `/broadcast_status ID` |
| 9 | `/stop_broadcast ID` | рассылка останавливается |
| 10 | `/last` | последняя рассылка видна в списке |

После smoke-теста token, который попал в чат/скриншот/лог, считается
скомпрометированным. Его нужно перевыпустить в BotFather.

## Troubleshooting

- `Missing required env var` — не заполнена переменная в `.env`.
- `ADMIN_IDS is empty` — нет ни одного админа.
- Админ-команды молча игнорируются — Telegram ID не добавлен в `ADMIN_IDS`.
- `TelegramUnauthorizedError` — token неверный или отозван.
- `TelegramConflictError` — тот же bot token запущен в другом процессе/на другом сервере.
- `database is locked` — проверьте, что нет второго процесса `app.main`.
- Рассылка зависла в `processing` после падения — перезапустить сервис, она станет `interrupted`.
- `Сессия истекла или не ваша` — preview рассылки был в памяти процесса; запустить `/broadcast` заново.

## Production deploy

Production путь: VPS + systemd. Fly/Render файлы в репо оставлены только как
optional staging/handoff examples. Не запускать VPS и Fly/Render одновременно
на одних и тех же bot tokens.

Пример unit-файла:

```ini
[Unit]
Description=tg_backup_bots (reviews + private)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=tgbots
Group=tgbots
WorkingDirectory=/opt/tg_backup_bots
EnvironmentFile=/opt/tg_backup_bots/.env
ExecStart=/opt/tg_backup_bots/.venv/bin/python -m app.main
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/tg_backup_bots
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
LockPersonality=true

[Install]
WantedBy=multi-user.target
```

База лежит рядом с `DATABASE_PATH`. Для production VPS сейчас используется:

```text
/opt/tg-backup-bots/data/bots.db
```

Бэкапить нужно `bots.db` и, если есть, `bots.db-wal` / `bots.db-shm`.
