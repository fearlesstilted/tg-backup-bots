# Release checklist

## Before commit

- [ ] `python3 -m compileall app tests` — no syntax errors.
- [ ] `.venv/bin/python -m unittest discover -s tests` — all tests pass.
- [ ] `.venv/bin/python -m app.simulate_broadcast --db /tmp/tg_backup_sim.db --users 100 --bot reviews --segment test` — completes with `Status=completed`.
- [ ] `.venv/bin/python -m app.healthcheck` — exits `0`, prints `OK preflight` (skip if you haven't set up `.env` locally — the missing-env path is exercised by tests).
- [ ] `git status --short` — only intentional source/test/doc files are listed.
- [ ] `git status --ignored --short | grep '^!! '` includes `.env`, `bots.db`, `bots.db-wal`, `bots.db-shm`, `bots.db.lock` if they exist. None of those must appear under `??`.

## Before production

- [ ] Rotate any bot token that was pasted into a chat, screenshot, ticket, log line, or PR description during smoke testing. In @BotFather: `/revoke` for each bot, then copy the new tokens into the production `.env`.
- [ ] Update `.env` on the deploy host. `chmod 600 .env`. Never commit it.
- [ ] `python -m app.healthcheck` on the deploy host — exits `0`.
- [ ] `systemctl daemon-reload && systemctl restart tg-backup-bots`.
- [ ] `journalctl -u tg-backup-bots -f` — confirm both bots start polling, no `TelegramUnauthorizedError`, no `TelegramConflictError`, no `AlreadyRunningError`.
- [ ] Smoke a single `/start <segment>` from a personal account against each bot; confirm opt-in link is delivered.
- [ ] Back up `bots.db` (and `-wal` / `-shm` siblings if present) to off-host storage. Re-run the backup whenever broadcasts grow significantly.
