from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.single_instance import (
    AlreadyRunningError,
    SingleInstanceLock,
    lock_path_for,
)


class SingleInstanceLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "x.lock")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_second_acquire_in_same_process_raises(self) -> None:
        first = SingleInstanceLock(self.path)
        first.acquire()
        try:
            second = SingleInstanceLock(self.path)
            with self.assertRaises(AlreadyRunningError):
                second.acquire()
        finally:
            first.release()

    def test_release_then_reacquire_succeeds(self) -> None:
        a = SingleInstanceLock(self.path)
        a.acquire()
        a.release()
        b = SingleInstanceLock(self.path)
        b.acquire()
        b.release()

    def test_context_manager_releases_on_exit(self) -> None:
        with SingleInstanceLock(self.path):
            pass
        # After exit, a fresh acquire must succeed.
        with SingleInstanceLock(self.path):
            pass

    def test_lock_file_records_pid(self) -> None:
        with SingleInstanceLock(self.path):
            content = Path(self.path).read_text().strip()
        self.assertEqual(content, str(os.getpid()))

    def test_lock_path_helper(self) -> None:
        self.assertEqual(lock_path_for("/var/x/bots.db"), "/var/x/bots.db.lock")


if __name__ == "__main__":
    unittest.main()
