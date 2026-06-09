# Интеграция сайта ShmaliShop и tg_backup_bots

Этот документ описывает контракт между сайтом ShmaliShop и двумя backup-ботами.

Reviews links публичные и могут храниться как статические значения в
`site_settings`. Private links в production должны выдаваться через подписанный
short token, иначе скопированная ссылка вида `privatesegment_bot?start=ru_private`
даёт доступ к приватному invite.

## Боты

> Перед production заменить временные usernames на финальные usernames из
> BotFather во всём документе и в `site_settings`.

| Bot kind | Telegram handle |
| --- | --- |
| `reviews` | `@reviewsegment_bot` |
| `private` | `@privatesegment_bot` |

Формат deep-link остаётся тем же:

```text
https://t.me/<bot_username>?start=<segment>
```

## Ключи `site_settings`, которые читает сайт

| Setting key | Где используется | Когда показывается |
| --- | --- | --- |
| `reviews_tg_url_ru` / `_en` / `_de` | `src/components/Header.tsx` | кнопка отзывов в header |
| `private_tg_url_ru` / `_en` / `_de` | `src/pages/Profile.tsx` | VIP кнопка в профиле, только если `hasPaidOrders=true` |

Обе группы редактируются в админке сайта:

```text
/admin/links → AdminSupportLinks
```

## Значения для Reviews

Reviews bot публичный, эти ссылки можно использовать статически:

| Key | Value |
| --- | --- |
| `reviews_tg_url_ru` | `https://t.me/reviewsegment_bot?start=ru_reviews` |
| `reviews_tg_url_en` | `https://t.me/reviewsegment_bot?start=foreign_reviews` |
| `reviews_tg_url_de` | `https://t.me/reviewsegment_bot?start=foreign_reviews` |

## Значения для Private

Эти static links подходят только для staging/smoke, пока:

```text
PRIVATE_REQUIRE_ACCESS_TOKEN=false
```

| Key | Value |
| --- | --- |
| `private_tg_url_ru` | `https://t.me/privatesegment_bot?start=ru_private` |
| `private_tg_url_en` | `https://t.me/privatesegment_bot?start=foreign_private` |
| `private_tg_url_de` | `https://t.me/privatesegment_bot?start=foreign_private` |

Для production нужно включить:

```text
PRIVATE_REQUIRE_ACCESS_TOKEN=true
```

Тогда сайт должен вызывать Supabase Edge Function
`create-telegram-access-token`. Она должна:

1. требовать `Authorization` header (`verify_jwt=true`);
2. получать текущего пользователя через `auth.getUser()`;
3. service-role key проверять `orders`;
4. пропускать только если есть заказ с `payment_status='paid'` или `status='completed'`;
5. принимать body `{ "segment": "ru_private" | "foreign_private" }`;
6. отклонять любые другие сегменты;
7. подписывать короткий token через `TELEGRAM_PRIVATE_ACCESS_SECRET`;
8. возвращать `{ "url": "https://t.me/<PRIVATE_BOT_USERNAME>?start=<token>" }`.

Формат token:

```text
v1.<segment-code>.<expiry-base36>.<hmac-signature>
```

Текущие segment codes:

- `rp` → `ru_private`
- `fp` → `foreign_private`

TTL: 10 минут. Secret должен жить только в Supabase/VPS env-vars, не в React.

## Production env vars

Supabase function:

- `TELEGRAM_PRIVATE_ACCESS_SECRET`
- `PRIVATE_BOT_USERNAME`

VPS с ботом:

- `PRIVATE_ACCESS_SECRET`
- `PRIVATE_REQUIRE_ACCESS_TOKEN=true`

`TELEGRAM_PRIVATE_ACCESS_SECRET` и `PRIVATE_ACCESS_SECRET` должны совпадать.

## Важный fallback EN/DE

В `src/components/Header.tsx` есть fallback на RU, если EN/DE ключ пустой:

```ts
const publicReviewsUrl = getSafeUrl(settings?.[`reviews_tg_url_${langCode}`] || settings?.['reviews_tg_url_ru']);
const privateGroupUrl  = getSafeUrl(settings?.[`private_tg_url_${langCode}`]  || settings?.['private_tg_url_ru']);
```

Если `_en` или `_de` не заполнить, англоязычный/немецкий пользователь может
получить RU deep-link. Поэтому нужно явно заполнить все 6 ключей.

В `src/pages/Profile.tsx` аналогичный fallback для `vipUrl`.

## Как обновить значения

Вариант A — через админку:

1. Зайти на сайт как admin.
2. Открыть `/admin/links`.
3. Вставить все 6 ссылок.
4. Сохранить.

Вариант B — через Supabase SQL:

1. Открыть Supabase → SQL editor.
2. Вставить [integration/site_settings_upsert.sql](integration/site_settings_upsert.sql).
3. Запустить.

Изменения применяются после reload сайта.

## Smoke test

| # | Язык | Действие на сайте | Ожидание |
| --- | --- | --- | --- |
| 1 | RU | Header → `Отзывы` | reviews bot открывается с `ru_reviews` |
| 2 | EN | Header → `Reviews` | reviews bot открывается с `foreign_reviews` |
| 3 | DE | Header → `Reviews` | reviews bot открывается с `foreign_reviews` |
| 4 | RU paid | Profile → VIP button | private bot открывается с `ru_private` или signed token на RU |
| 5 | EN paid | Profile → VIP button | private bot открывается с `foreign_private` или signed token на Foreign |
| 6 | DE paid | Profile → VIP button | как EN |

После каждого теста проверить в SQLite `users`: правильные `bot_kind`,
`segment`, `opted_in=1`.

## Ротация tokens

Перед production:

1. Перевыпустить tokens в BotFather (`/revoke`), если они попадали в чат/скриншот/лог.
2. Обновить `.env` на VPS.
3. Перезапустить сервис.
4. Обновить 6 значений в `site_settings`, если изменились usernames.
5. Повторить smoke test.
