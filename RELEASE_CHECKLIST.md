# Release checklist

## Перед commit

- [ ] `python3 -m compileall app tests` — нет syntax errors.
- [ ] `.venv/bin/python -m unittest discover -s tests` — тесты проходят.
- [ ] `.venv/bin/python -m app.simulate_broadcast --db /tmp/tg_backup_sim.db --users 100 --bot reviews --segment test` — simulation завершается со статусом `completed`.
- [ ] `.venv/bin/python -m app.healthcheck` — exit code `0`, выводит `OK preflight`.
- [ ] `git status --short` — только ожидаемые source/test/doc изменения.
- [ ] `.env`, `bots.db`, `bots.db-wal`, `bots.db-shm`, `bots.db.lock`, `backups/` не попали в git.

## Перед production

- [ ] Перевыпустить bot token, если он попадал в чат, скриншот, ticket, log или PR description.
- [ ] В BotFather: `/revoke` для каждого скомпрометированного бота.
- [ ] Обновить `.env` на VPS.
- [ ] `chmod 600 .env`.
- [ ] Для private-chat production access включить `PRIVATE_REQUIRE_ACCESS_TOKEN=true`.
- [ ] Задать новый длинный `PRIVATE_ACCESS_SECRET`.
- [ ] Убедиться, что такой же secret задан на серверной стороне сайта/Supabase function.
- [ ] Запустить `python -m app.healthcheck` на VPS.
- [ ] Выполнить `systemctl daemon-reload && systemctl restart tg-backup-bots`.
- [ ] Проверить `journalctl -u tg-backup-bots -f`.
- [ ] Убедиться, что нет `TelegramUnauthorizedError`.
- [ ] Убедиться, что нет `TelegramConflictError`.
- [ ] Убедиться, что нет второго процесса с теми же bot tokens.
- [ ] Сделать smoke test `/start <segment>` в каждом боте.
- [ ] Проверить, что opt-in выдаёт правильную ссылку.
- [ ] Проверить `/stats`, `/broadcast`, `Dry-run`, `/last`.
- [ ] Сделать backup `bots.db` и, если есть, `-wal` / `-shm`.
