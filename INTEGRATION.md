# ShmaliShop site ↔ tg_backup_bots integration

This document is the contract between the ShmaliShop frontend and the two backup bots. **The site needs no code changes** — both link groups are admin-editable settings stored in Supabase `site_settings` as `(key, value)` pairs. Updating the bots = updating six string values.

## Bots

| Bot kind | Telegram handle |
| --- | --- |
| `reviews` | `@reviewsegment_bot` |
| `private` | `@privatesegment_bot` |

> The handles above are temporary while we iterate. Re-issuing a bot in @BotFather changes only the username — the same `?start=<segment>` deep-link format keeps working, you just refresh the six values below.

## Settings keys used by the site

| Setting key | Used in | Rendered to user when |
| --- | --- | --- |
| `reviews_tg_url_ru` / `_en` / `_de` | `src/components/Header.tsx` (publicReviewsUrl) | Reviews button in header, language-matched |
| `private_tg_url_ru` / `_en` / `_de` | `src/pages/Profile.tsx` (vipUrl) | "Join VIP" button on the profile page, shown only when `hasPaidOrders` is true |

Both groups are admin-editable in the site admin UI: **`/admin/links` → AdminSupportLinks**.

## Values to paste

### Reviews (public — anyone can use)

| Key | Value |
| --- | --- |
| `reviews_tg_url_ru` | `https://t.me/reviewsegment_bot?start=ru_reviews` |
| `reviews_tg_url_en` | `https://t.me/reviewsegment_bot?start=foreign_reviews` |
| `reviews_tg_url_de` | `https://t.me/reviewsegment_bot?start=foreign_reviews` |

### Private (VIP — only paid users see the button)

| Key | Value |
| --- | --- |
| `private_tg_url_ru` | `https://t.me/privatesegment_bot?start=ru_private` |
| `private_tg_url_en` | `https://t.me/privatesegment_bot?start=foreign_private` |
| `private_tg_url_de` | `https://t.me/privatesegment_bot?start=foreign_private` |

The `FOREIGN_PRIVATE_LINK` in the bot's `.env` is the invite the user receives after opt-in.

## Gotcha: the Header EN/DE fallback

`src/components/Header.tsx:74-75` falls back to the `_ru` variant if the language-specific key is empty:

```ts
const publicReviewsUrl = getSafeUrl(settings?.[`reviews_tg_url_${langCode}`] || settings?.['reviews_tg_url_ru']);
const privateGroupUrl  = getSafeUrl(settings?.[`private_tg_url_${langCode}`]  || settings?.['private_tg_url_ru']);
```

This means: **if `_en` or `_de` is missing in `site_settings`, an EN/DE user gets the RU deep link** — i.e. an EN-language user joining "reviews" would land in `ru_reviews`. Always set all three language keys explicitly, even when the value is identical.

(`src/pages/Profile.tsx:417-421` has the same fallback chain for `vipUrl`.)

`getSafeUrl` only trims surrounding quotes and prepends `https://` if missing — `?start=…` query strings pass through unchanged.

## Updating the values

Two equivalent options:

### Option A — admin UI (3 minutes, no SQL)

1. Log in to the site as an admin.
2. Open `/admin/links`.
3. Paste each of the six values into the matching field.
4. Save.

### Option B — Supabase SQL editor

See [`integration/site_settings_upsert.sql`](integration/site_settings_upsert.sql). Open Supabase → SQL editor → paste → run. Idempotent (`ON CONFLICT (key) DO UPDATE`).

Either way, the change takes effect on the next site reload (the `useSiteSettings` hook fetches once and caches in-memory).

## Click-through smoke test

After updating, verify each (language × segment) pair end-to-end. The site does **not** need to be redeployed — the settings hook refetches on page load.

| # | Browser language | Site action | Expected Telegram bot behaviour |
| --- | --- | --- | --- |
| 1 | RU | Header → "Отзывы" | `@reviewsegment_bot` opens, `/start ru_reviews`, opt-in → RU reviews invite link |
| 2 | EN | Header → "Reviews" | `@reviewsegment_bot` opens, `/start foreign_reviews`, opt-in → foreign reviews invite link |
| 3 | DE | Header → "Reviews" | same as EN (`foreign_reviews`) |
| 4 | RU (paid) | Profile → "Join VIP" | `@privatesegment_bot` opens, `/start ru_private`, opt-in → RU private invite link |
| 5 | EN (paid) | Profile → "Join VIP" | `@privatesegment_bot` opens, `/start foreign_private`, opt-in → foreign private invite link |
| 6 | DE (paid) | Profile → "Join VIP" | same as EN |

After each test, check the corresponding row in `users` (DB) has `bot_kind`, `segment`, and `opted_in=1` set correctly. The full live smoke checklist is in [README.md → Live smoke test checklist](README.md#live-smoke-test-checklist).

## Token rotation

The handles `reviewsegment_bot` / `privatesegment_bot` will be reissued before production. When that happens:

1. Revoke the old tokens in @BotFather (`/revoke`).
2. Update `.env` on the bot host with the new tokens.
3. Restart the bot service.
4. Update the six `site_settings` values to point at the new handles.
5. Re-run the click-through smoke test above.
