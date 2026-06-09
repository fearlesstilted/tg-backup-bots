# Telegram Backup Bots — инструкция для клиента

## Что это

Система состоит из двух Telegram-ботов:

- **Reviews bot** — для каналов отзывов: `ru_reviews`, `foreign_reviews`.
- **Private bot** — для приватных чатов: `ru_private`, `foreign_private`.

Пользователь открывает персональную ссылку на нужный сегмент, нажимает кнопку подтверждения и получает актуальную ссылку. После этого админ может отправить emergency-рассылку только нужному сегменту.

## Тексты для пользователей

RU:

```text
Привет! Это резервный бот ShmaliShop.

Нажмите кнопку ниже, чтобы подтвердить подписку. Если основной чат или канал будет недоступен, мы пришлём сюда актуальную ссылку.
```

EN:

```text
Hi! This is the ShmaliShop backup bot.

Tap the button below to confirm your subscription. If the main chat or channel becomes unavailable, we will send the updated link here.
```

## Что закрепить в чатах

RU private:

```text
Чтобы не потерять доступ, если чат будет недоступен, нажмите кнопку и подтвердите подписку в резервном боте.
```

Foreign private:

```text
To keep access if this chat becomes unavailable, open the backup bot and confirm your subscription.
```

Reviews RU:

```text
Подпишитесь на резервный бот, чтобы получать актуальную ссылку на отзывы.
```

Reviews EN:

```text
Subscribe to the backup bot to receive the current reviews link.
```

## Админ-панель в Telegram

У админа есть кнопки:

- `📊 Статистика` — сколько пользователей в каждом сегменте.
- `📜 Последние` — последние рассылки и результаты.
- `📣 Рассылка RU` — начать рассылку в RU-сегмент текущего бота.
- `📣 Рассылка Foreign` — начать рассылку в foreign-сегмент текущего бота.
- `ℹ️ Помощь` — короткая справка.

Команды тоже остаются:

- `/menu`
- `/stats`
- `/last`
- `/broadcast <segment>`
- `/broadcast_status <id>`
- `/stop_broadcast <id>`
- `/test <segment>`

## Как отправить рассылку

1. Открыть нужного бота: Reviews или Private.
2. Нажать `📣 Рассылка RU` или `📣 Рассылка Foreign`.
3. Отправить текст сообщения.
4. Бот покажет preview и количество получателей.
5. Нажать `Dry-run`, если нужно проверить без отправки.
6. Нажать `Отправить`, если всё верно.
7. Проверить результат через `📜 Последние` или `/broadcast_status <id>`.

## Где хранится база пользователей

База хранится на VPS в SQLite-файле:

```text
/opt/tg-backup-bots/bots.db
```

В базе лежат:

- Telegram ID пользователя;
- username / first name, если Telegram их отдаёт;
- язык пользователя;
- сегмент (`ru_reviews`, `foreign_reviews`, `ru_private`, `foreign_private`);
- статус подписки;
- активен ли пользователь для рассылок.

Токены ботов и приватные ссылки **не хранятся в git**. Они лежат только в `.env` на сервере.

## Бэкапы

На VPS настроен ежедневный бэкап базы:

```text
/opt/tg-backup-bots/backups/
```

Бэкап нужен, чтобы не потерять базу подписчиков при сбое сервера.

## Важные правила

- Не отправлять production bot tokens в чаты и скриншоты.
- Не давать admin access посторонним Telegram ID.
- Перед большой рассылкой сначала использовать `Dry-run`.
- Приватные ссылки на закрытые чаты не публиковать публично, только через private bot.
