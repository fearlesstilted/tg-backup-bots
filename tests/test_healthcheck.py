from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import healthcheck
from app.config import Settings


def _good_env(db_path: str) -> dict:
    return {
        "REVIEWS_BOT_TOKEN": "111:fake",
        "PRIVATE_BOT_TOKEN": "222:fake",
        "ADMIN_IDS": "42",
        "DATABASE_PATH": db_path,
        "RU_REVIEWS_LINK": "https://t.me/+ru_rev",
        "FOREIGN_REVIEWS_LINK": "https://t.me/+for_rev",
        "RU_PRIVATE_LINK": "https://t.me/+ru_priv",
        "FOREIGN_PRIVATE_LINK": "https://t.me/+for_priv",
    }


class _NoDotenv:
    """Disable dotenv side effects so tests rely purely on patched env."""

    def __enter__(self):
        self.p = patch("app.config.load_dotenv", lambda *a, **kw: False)
        self.p.start()
        return self

    def __exit__(self, *exc):
        self.p.stop()


class HealthcheckTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, env: dict) -> tuple[int, str]:
        out = io.StringIO()
        with _NoDotenv(), patch.dict(os.environ, env, clear=True):
            rc = await healthcheck._check(out)
        return rc, out.getvalue()

    async def test_happy_path_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "h.db")
            rc, text = await self._run(_good_env(db))
        self.assertEqual(rc, 0, msg=text)
        self.assertIn("OK preflight", text)
        self.assertIn("journal_mode  = wal", text)
        self.assertIn("admin_ids        = 1 configured", text)

    async def test_missing_env_var_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _good_env(str(Path(tmp) / "h.db"))
            env.pop("REVIEWS_BOT_TOKEN")
            rc, text = await self._run(env)
        self.assertEqual(rc, 2)
        self.assertIn("FAIL config", text)
        self.assertIn("REVIEWS_BOT_TOKEN", text)

    async def test_empty_admin_ids_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _good_env(str(Path(tmp) / "h.db"))
            env["ADMIN_IDS"] = ""
            rc, text = await self._run(env)
        self.assertEqual(rc, 2)
        self.assertIn("ADMIN_IDS is empty", text)

    async def test_invalid_admin_ids_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _good_env(str(Path(tmp) / "h.db"))
            env["ADMIN_IDS"] = "42,not-a-number"
            rc, text = await self._run(env)
        self.assertEqual(rc, 2)
        self.assertIn("FAIL config", text)
        self.assertIn("ADMIN_IDS must be a comma-separated list", text)

    async def test_placeholder_values_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _good_env(str(Path(tmp) / "h.db"))
            env["PRIVATE_BOT_TOKEN"] = "123456:replace-me"
            env["FOREIGN_PRIVATE_LINK"] = "https://t.me/+foreign_private_invite"
            rc, text = await self._run(env)
        self.assertEqual(rc, 2)
        self.assertIn("FAIL config", text)
        self.assertIn("PRIVATE_BOT_TOKEN", text)
        self.assertIn("FOREIGN_PRIVATE_LINK", text)

    async def test_private_token_enforcement_requires_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _good_env(str(Path(tmp) / "h.db"))
            env["PRIVATE_REQUIRE_ACCESS_TOKEN"] = "true"
            env["PRIVATE_ACCESS_SECRET"] = "generate-long-random-secret-before-production"
            rc, text = await self._run(env)
        self.assertEqual(rc, 2)
        self.assertIn("PRIVATE_ACCESS_SECRET", text)

    async def test_placeholder_secret_warns_when_not_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _good_env(str(Path(tmp) / "h.db"))
            env["PRIVATE_REQUIRE_ACCESS_TOKEN"] = "false"
            env["PRIVATE_ACCESS_SECRET"] = "generate-long-random-secret-before-production"
            rc, text = await self._run(env)
        self.assertEqual(rc, 0, msg=text)
        self.assertIn("WARN config: PRIVATE_ACCESS_SECRET", text)


class SettingsLoadTests(unittest.TestCase):
    def test_missing_required_var_raises(self) -> None:
        env = _good_env("/tmp/whatever.db")
        env.pop("RU_PRIVATE_LINK")
        with _NoDotenv(), patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                Settings.load()
        self.assertIn("RU_PRIVATE_LINK", str(ctx.exception))

    def test_admin_ids_parsed_as_ints(self) -> None:
        env = _good_env("/tmp/whatever.db")
        env["ADMIN_IDS"] = "1, 2,  3"
        with _NoDotenv(), patch.dict(os.environ, env, clear=True):
            s = Settings.load()
        self.assertEqual(s.admin_ids, frozenset({1, 2, 3}))

    def test_private_token_flags_parse(self) -> None:
        env = _good_env("/tmp/whatever.db")
        env["PRIVATE_REQUIRE_ACCESS_TOKEN"] = "yes"
        env["PRIVATE_ACCESS_SECRET"] = "real-secret"
        with _NoDotenv(), patch.dict(os.environ, env, clear=True):
            s = Settings.load()
        self.assertTrue(s.private_require_access_token)
        self.assertEqual(s.private_access_secret, "real-secret")

    def test_invalid_admin_ids_raise_runtime_error(self) -> None:
        env = _good_env("/tmp/whatever.db")
        env["ADMIN_IDS"] = "1,nope"
        with _NoDotenv(), patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                Settings.load()
        self.assertIn("ADMIN_IDS must be a comma-separated list", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
