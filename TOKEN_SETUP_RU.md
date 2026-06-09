# Как создать новые Telegram bot tokens

Эта инструкция для человека, который владеет Telegram-ботами.

## 1. Открыть BotFather

В Telegram открыть:

```text
@BotFather
```

## 2. Создать Reviews bot

1. Написать:

```text
/newbot
```

2. Ввести имя, например:

```text
ShmaliShop Reviews Backup
```

3. Ввести username, он должен заканчиваться на `bot`, например:

```text
shmalishop_reviews_backup_bot
```

4. BotFather выдаст token. Его нужно отправить разработчику **только в личку**, не в общий чат.

## 3. Создать Private bot

Повторить то же самое:

```text
/newbot
```

Имя:

```text
ShmaliShop Private Backup
```

Username:

```text
shmalishop_private_backup_bot
```

Token тоже отправить только в личку.

## 4. Что нельзя делать

- Не отправлять token в групповые чаты.
- Не делать скриншот token.
- Не коммитить token в GitHub.
- Не давать token людям, которые не должны управлять ботом.

Если token случайно попал в чат или на скриншот, его нужно перевыпустить.

## 5. Как перевыпустить token

В `@BotFather`:

```text
/revoke
```

Выбрать нужного бота. BotFather выдаст новый token. Старый token перестанет работать.

## 6. Что передать для production launch

Нужно передать:

- token Reviews bot;
- token Private bot;
- Telegram ID админов, которым можно запускать рассылки;
- актуальные ссылки для сегментов:
  - RU reviews;
  - Foreign reviews;
  - RU private;
  - Foreign private.

После этого разработчик обновляет `.env` на VPS и перезапускает сервис.
