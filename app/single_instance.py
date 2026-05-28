"""Single-instance lock via fcntl.flock.

Prevents two app.main processes from polling the same bot tokens against the
same DATABASE_PATH on one host — which manifests as TelegramConflictError
("terminated by other getUpdates request") and as `database is locked`
contention on writes.

The lock file lives next to DATABASE_PATH (<DATABASE_PATH>.lock). The fd is
kept open for the lifetime of the process; on exit the OS releases the lock.
flock is advisory and per-fd, so this only protects against other processes
that take the same lock (i.e. another app.main on the same machine). It does
NOT defend against a second machine using the same tokens — see the
TelegramConflictError troubleshooting entry for that case.
"""

from __future__ import annotations

import errno
import fcntl
import os
from typing import Optional


class AlreadyRunningError(RuntimeError):
    pass


class SingleInstanceLock:
    def __init__(self, path: str) -> None:
        self.path = path
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise AlreadyRunningError(
                    f"Another instance is already holding {self.path}. "
                    "Run `ps -ef | grep app.main` and stop the duplicate."
                ) from e
            raise
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def lock_path_for(database_path: str) -> str:
    return database_path + ".lock"
