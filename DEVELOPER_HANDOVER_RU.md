# Инструкция для разработчика

## Назначение проекта

`tg_backup_bots` — отдельный сервис с двумя Telegram-ботами:

- `reviews` — бот для каналов отзывов: `ru_reviews`, `foreign_reviews`.
- `private` — бот для приватных чатов: `ru_private`, `foreign_private`.

Бот сохраняет пользователя в SQLite-базу после `/start <segment>` и подтверждения кнопкой. Админ может отправить рассылку по конкретному сегменту.

## Основные файлы

- `app/main.py` — запуск двух ботов в одном процессе.
- `app/config.py` — env-настройки, сегменты, ссылки.
- `app/db.py` — схема SQLite, WAL, подключение к базе.
- `app/handlers/user.py` — `/start`, `/stop`, приветственный текст, opt-in.
- `app/handlers/admin.py` — `/menu`, `/stats`, `/broadcast`, `/last`, `/test`.
- `app/keyboards.py` — кнопки пользователей и админ-меню.
- `app/services/broadcasts.py` — движок рассылок, rate limit, retries, логи.
- `app/services/users.py` — операции с пользователями.

## Где менять приветственный текст

Файл:

```text
app/handlers/user.py
```

Переменные:

```python
OPTIN_TEXT_RU
OPTIN_TEXT_EN
UNKNOWN_TEXT_RU
UNKNOWN_TEXT_EN
```

Кнопка подтверждения меняется в:

```text
app/keyboards.py
```

Функция:

```python
optin_keyboard(segment)
```

Сейчас RU-сегменты получают кнопку `✅ Подтвердить`, foreign-сегменты получают `✅ Confirm`.

## Где хранится база

На production VPS:

```text
/opt/tg-backup-bots/bots.db
```

Это SQLite. Включён WAL. База хранит пользователей, рассылки и delivery-логи.

## Где лежат секреты

Секреты не должны быть в git. На сервере они лежат в:

```text
/opt/tg-backup-bots/.env
```

Там находятся bot tokens, admin ids, ссылки сегментов и private access secret.

## Проверки перед деплоем

```bash
python3 -m compileall app tests
.venv/bin/python3 -m unittest discover -s tests
.venv/bin/python3 -m app.healthcheck
```

## Production service

Systemd-сервис:

```text
tg-backup-bots.service
```

Базовые команды:

```bash
sudo systemctl status tg-backup-bots
sudo systemctl restart tg-backup-bots
sudo journalctl -u tg-backup-bots -n 100 --no-pager
```

## Важные правила

- Не коммитить `.env`, `bots.db`, `*.db-wal`, `*.db-shm`.
- Не запускать два процесса с одинаковыми bot tokens.
- Перед массовой рассылкой использовать `Dry-run`.
- Production private links не публиковать в публичных местах.
