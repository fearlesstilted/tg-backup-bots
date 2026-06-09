# tg_backup_bots

MVP of two Telegram backup bots (Reviews + Private), each serving a RU and a Foreign segment. Built on aiogram 3 + SQLite.

## Site integration

The ShmaliShop frontend (separate repo, `smalishop/`) reads six bot deep links from Supabase `site_settings` and renders them as language-matched buttons. **No frontend code change is needed** to wire these bots in — only six settings values. Full contract, exact values to paste, EN/DE fallback gotcha, click-through smoke plan, and a ready Supabase SQL snippet:

- [INTEGRATION.md](INTEGRATION.md)
- [integration/site_settings_upsert.sql](integration/site_settings_upsert.sql)

## Setup

Python 3.11+.

```bash
cd tg_backup_bots
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env             # keep tokens off other users
$EDITOR .env               # fill REVIEWS_BOT_TOKEN, PRIVATE_BOT_TOKEN, ADMIN_IDS, *_LINK
```

`.env` is in `.gitignore` — never commit it. If a token leaks to git history, revoke it in @BotFather and rotate before pushing.

## Run

Single process drives both bots:

```bash
python -m app.main
```

## Environment variables

| Var | Purpose |
| --- | --- |
| `REVIEWS_BOT_TOKEN` | Bot token for the reviews bot |
| `PRIVATE_BOT_TOKEN` | Bot token for the private bot |
| `ADMIN_IDS` | Comma-separated Telegram user IDs allowed to run admin commands |
| `DATABASE_PATH` | SQLite file path (default `./bots.db`) |
| `PRIVATE_REQUIRE_ACCESS_TOKEN` | If `true`, the private bot rejects raw `ru_private` / `foreign_private` starts and requires signed short tokens |
| `PRIVATE_ACCESS_SECRET` | Shared HMAC secret used to validate private bot access tokens |
| `RU_REVIEWS_LINK` / `FOREIGN_REVIEWS_LINK` | Invite links sent after opt-in (reviews bot) |
| `RU_PRIVATE_LINK` / `FOREIGN_PRIVATE_LINK` | Invite links sent after opt-in (private bot) |

## User flow

`/start <segment>` upserts the user, shows an opt-in button. After tapping, the user is marked `opted_in=1, is_active=1` and receives the matching invite link.

Allowed segments per bot:

- reviews bot: `ru_reviews`, `foreign_reviews`, `test`
- private bot: `ru_private`, `foreign_private`, `test`

Anything else is stored as `unknown` and the user gets a neutral fallback message (no link).

For production private-chat access, set `PRIVATE_REQUIRE_ACCESS_TOKEN=true`.
Then the private bot will only accept a short signed token in `/start`, for
example `https://t.me/privatesegment_bot?start=v1.rp...`. Raw links like
`?start=ru_private` should stay disabled in production because browser-visible
links can be copied by non-paying users. The token must be generated server-side
by the site after checking that the user has a paid order; never generate it in
frontend JavaScript because that would leak `PRIVATE_ACCESS_SECRET`.

For manual smoke tests you can generate one token locally:

```bash
PRIVATE_ACCESS_SECRET=... .venv/bin/python -m app.access_tokens ru_private 600
```

## Admin commands

Restricted to `ADMIN_IDS`:

- `/menu` — show the Telegram button menu for admins.
- `/stats` — per-segment counts (total / opted-in / active) for the current bot.
- `/broadcast <segment>` — start a broadcast: bot prompts for text, shows a preview with recipient count and Confirm / Dry-run / Cancel buttons.
- `/broadcast_status <id>` — current status and counters.
- `/stop_broadcast <id>` — request stop; running loop checks every 50 sends.
- `/last` — last 10 broadcasts for this bot.
- `/test <segment>` — send the next message only to yourself (formatting check before a real broadcast).

The same core actions are also available as Telegram buttons for admins:
`📊 Статистика`, `📜 Последние`, `📣 Рассылка RU`, `📣 Рассылка Foreign`, `ℹ️ Помощь`.

## Broadcast engine

- ~18 msg/sec target (one `asyncio.sleep` between sends), not `gather`.
- `TelegramRetryAfter` → sleep and retry same user, up to 3 retries.
- `TelegramForbiddenError` / "chat not found" / "user is deactivated" → mark user inactive (`blocked` counter).
- Other errors → counted as `failed`, user kept active.
- Delivery rows and counter updates flushed in batches of 50, single transaction.
- Stop flag re-read from DB every 50 sends.
- On startup, any broadcast left in `processing` is marked `interrupted`.

## Simulate

Drives the real broadcast engine with a stub sender — no Telegram, no tokens:

```bash
python -m app.simulate_broadcast --db ./sim.db --users 1000 --bot reviews --segment test
```

Reports observed send rate, final status, and counters.

## Preflight before Telegram polling

Run the no-network preflight whenever you change `.env`, before starting polling for real. It loads `Settings`, verifies admin ids and links are present, opens the DB (applying schema and confirming WAL), and prints a summary. Exit code 0 means safe to start.

```bash
.venv/bin/python -m app.healthcheck
```

Exit codes: `0` ok, `2` config problem, `3` database problem.

## Troubleshooting

- **`FAIL config: Missing required env var: X`** — env var not exported and absent from `.env`. Check the variable name in `.env.example`.
- **`FAIL config: ADMIN_IDS is empty`** — set at least one Telegram user id. Find yours by messaging [@userinfobot](https://t.me/userinfobot).
- **`FAIL config: ADMIN_IDS must be a comma-separated list`** — remove usernames, spaces-only entries, or other non-numeric values; use Telegram numeric user ids only.
- **Admin commands silently ignored** — your user id is not in `ADMIN_IDS`. The admin router filter drops the update; the user router doesn't claim it either. Verify with `/stats` from the correct account.
- **`TelegramUnauthorizedError` / 401 at startup** — bot token wrong or revoked. Regenerate in @BotFather and update `.env`.
- **`TelegramConflictError` / "terminated by other getUpdates request"** — another instance is polling the same token (local + systemd, two machines, leftover process). Stop the duplicate (`systemctl stop tg-backup-bots`, `pkill -f app.main`) before starting again. Polling and webhooks are mutually exclusive — `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook` if a webhook was ever set.
- **Duplicate local `app.main` process** — `app.main` now takes an advisory `fcntl` lock on `<DATABASE_PATH>.lock` and exits with code `4` and `Another instance is already holding …` if it can't acquire it. To find the holder: `ps -ef | grep app.main` (ignore the `grep` row), then `kill <pid>`. The lock is per host — it does not protect against a second machine using the same tokens (Telegram itself surfaces that as `TelegramConflictError`).
- **`sqlite3.OperationalError: database is locked`** — another process holds a write lock on `bots.db`. WAL + `busy_timeout=5000` covers normal contention; if it persists, ensure only one `app.main` runs against a given `DATABASE_PATH`.
- **Broadcast status stuck on `processing` after a crash** — restart `python -m app.main`; on startup leftover rows are flipped to `interrupted`.
- **`Sessions истекла или не ваша.` on broadcast confirm** — the pending broadcast is in process memory only; it's lost after a restart or when claimed by a different admin. Start `/broadcast <segment>` again.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests
python -m compileall app tests
```

Or via `make`:

```bash
make test       # unittest discover
make check      # compileall + unittest
make simulate   # 1000-user dry simulation
make health     # preflight against current .env
```

## Live smoke test checklist

Run only with real tokens, against accounts you control. The reviews bot and the private bot are exercised independently, both via the same `python -m app.main` process.

Setup:

1. `.env` filled with two real bot tokens, your own Telegram user id in `ADMIN_IDS`, and four real invite links.
2. `.venv/bin/python -m app.healthcheck` — must print `OK preflight` and exit 0.
3. `python -m app.main` — log line `Marked N stale broadcast(s) as interrupted.` may appear; followed by aiogram polling startup for both bots.
4. Open both bots in your personal Telegram client. Pre-create a second non-admin account if you want to validate the admin gate.

For each bot, run the matching segment (`ru_reviews`/`foreign_reviews` for reviews bot, `ru_private`/`foreign_private` for private bot):

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `/start ru_reviews` (in reviews bot) | Opt-in message + localized button: `✅ Подтвердить` for RU, `✅ Confirm` for Foreign. Row in `users` with `opted_in=0, is_active=1`. |
| 2 | Tap the button | Message edited to "Спасибо! Вот ваша ссылка: …" with the matching invite link. Row now `opted_in=1`. |
| 3 | `/start garbage` | Neutral fallback ("ссылка пришла без параметра"), no link. Row stored with `segment='unknown'`. |
| 4 | `/start ru_private` in **reviews** bot | Treated as `unknown` — cross-bot segment is rejected. |
| 5 | `/stats` (as admin) | One line per segment with `total / optin / active`. Non-admin gets no reply. |
| 6 | `/test ru_reviews` → send text | Bot asks for text, then sends it only to you. |
| 7 | `/broadcast ru_reviews` → send text → tap "🧪 Dry-run" | "Dry-run: было бы отправлено N сообщений …". No new broadcast row. |
| 8 | `/broadcast ru_reviews` → send text → tap "🚀 Отправить" | Reply "Рассылка #ID запущена". `/broadcast_status <ID>` shows growing `sent` counter. |
| 9 | `/stop_broadcast <ID>` mid-run | "Остановка запрошена.". Within ≤50 sends, `/broadcast_status <ID>` reports `stopped`. |
| 10 | `/last` | Top entry is the just-finished broadcast with final counters. |
| 11 | Kill the process during a broadcast, restart | On startup, the leftover row flips to `interrupted`. |

Repeat steps 1–10 against the private bot using `ru_private` / `foreign_private`.

**After live smoke** — any bot token that was pasted into a chat, screenshot, ticket, or log line during the smoke test must be considered leaked. Rotate both tokens in @BotFather (`/revoke`), update `.env`, restart the service, and re-run the preflight before going to production. See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for the full pre-commit / pre-production list.

## Deploy to Fly.io (free staging)

Fly.io's Hobby plan runs a small persistent worker for free (3 × shared-cpu / 256 MB VMs + 3 GB total volume storage). The repo ships [`fly.toml`](fly.toml) and a slim [`Dockerfile`](Dockerfile); SQLite + WAL + the single-instance lock live on a mounted volume so deploys don't lose state.

```bash
# 1. Install flyctl (one-time)
curl -L https://fly.io/install.sh | sh

# 2. Sign up / log in (asks for credit card — Free tier won't charge)
flyctl auth signup            # or: flyctl auth login

# 3. From inside tg_backup_bots/:
flyctl apps create tg-backup-bots          # pick a different name if taken — also edit fly.toml
flyctl volumes create tg_backup_data --region fra --size 1
flyctl secrets set \
  REVIEWS_BOT_TOKEN=...      PRIVATE_BOT_TOKEN=... \
  ADMIN_IDS=111,222          \
  RU_REVIEWS_LINK=https://t.me/+...   FOREIGN_REVIEWS_LINK=https://t.me/+... \
  RU_PRIVATE_LINK=https://t.me/+...   FOREIGN_PRIVATE_LINK=https://t.me/+...
flyctl deploy
flyctl logs                                # expect "Run polling for bot @… within ~30s"
```

**Single-instance**: Telegram allows only one polling consumer per token, so never run more than one machine. `fly.toml` already enables `strategy = "immediate"`; don't `flyctl scale count >1`.

**Backup**: pull the SQLite file from the volume periodically:

```bash
flyctl ssh console --command "sqlite3 /data/bots.db .dump" > backup-$(date +%F).sql
```

For paid staging on Render (Background Worker + persistent disk, ~$7/mo) see [`render.yaml`](render.yaml) and the section below.

## Deploy to Render (staging)

The repo ships [`render.yaml`](render.yaml) — a Render Blueprint that provisions a Background Worker + 1 GB persistent disk in one click. Background Workers are paid only (no free tier); current shape is `Starter` (~$7/mo) + disk (~$0.25/mo for 1 GB).

Steps:

1. In [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint** → connect the GitHub repo → pick the branch.
2. Render parses `render.yaml` and shows the missing secrets. Fill in:
   - `REVIEWS_BOT_TOKEN`, `PRIVATE_BOT_TOKEN` — from @BotFather.
   - `ADMIN_IDS` — comma-separated Telegram user IDs.
   - `RU_REVIEWS_LINK`, `FOREIGN_REVIEWS_LINK`, `RU_PRIVATE_LINK`, `FOREIGN_PRIVATE_LINK` — invite links to the actual channels/chats.
3. **Apply** → Render builds (`pip install -r requirements.txt`), mounts the disk, starts `python -m app.main`.
4. Logs: service page → **Logs**. Expect `aiogram.dispatcher: Run polling for bot @reviewsegment_bot` and `@privatesegment_bot` within ~30s.

Persistent disk is mounted at `/opt/render/project/src/data`; `DATABASE_PATH` is preset to `bots.db` inside it. SQLite WAL and the single-instance lock file live on the disk, so deploys/restarts don't lose state.

**Backup**: Render disks are reliable but not backed up by default. Periodically dump the DB off-host, e.g. from a Render Shell:

```bash
sqlite3 /opt/render/project/src/data/bots.db ".backup '/tmp/backup-$(date +%F).db'"
# then download via the Render Shell file browser or scp from your laptop
```

For VPS-based production deployment (no monthly Render bill), see the systemd section below — `render.yaml` is for staging/handoff convenience.

## Production deploy (systemd)

`.env`-driven, no extra config required. Example unit file at `/etc/systemd/system/tg-backup-bots.service`:

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

# Hardening
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

Install:

```bash
sudo useradd --system --home /opt/tg_backup_bots --shell /usr/sbin/nologin tgbots
sudo install -d -o tgbots -g tgbots /opt/tg_backup_bots
sudo -u tgbots rsync -a --exclude .venv --exclude '*.db*' ./ /opt/tg_backup_bots/
sudo -u tgbots python -m venv /opt/tg_backup_bots/.venv
sudo -u tgbots /opt/tg_backup_bots/.venv/bin/pip install -r /opt/tg_backup_bots/requirements.txt
sudo install -m 600 -o tgbots -g tgbots .env /opt/tg_backup_bots/.env
sudo systemctl daemon-reload
sudo systemctl enable --now tg-backup-bots.service
sudo journalctl -u tg-backup-bots -f
```

DB file lives under `WorkingDirectory` (`/opt/tg_backup_bots/bots.db` by default). Back up `bots.db` plus the `-wal` / `-shm` siblings if present.
