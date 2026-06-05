from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys
import time

TOKEN_VERSION = "v1"

SEGMENT_TO_CODE = {
    "ru_private": "rp",
    "foreign_private": "fp",
}
CODE_TO_SEGMENT = {v: k for k, v in SEGMENT_TO_CODE.items()}


class AccessTokenError(ValueError):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base36(value: int) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value < 0:
        raise ValueError("value must be non-negative")
    if value == 0:
        return "0"
    out = []
    while value:
        value, rem = divmod(value, 36)
        out.append(chars[rem])
    return "".join(reversed(out))


def _from_base36(value: str) -> int:
    try:
        return int(value, 36)
    except ValueError as e:
        raise AccessTokenError("Invalid token expiry") from e


def _sign(message: str, secret: str) -> str:
    if not secret:
        raise AccessTokenError("Access token secret is not configured")
    digest = hmac.new(secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256)
    return _b64url(digest.digest()[:16])


def create_access_token(
    segment: str,
    secret: str,
    *,
    ttl_seconds: int = 600,
    now: int | None = None,
) -> str:
    if segment not in SEGMENT_TO_CODE:
        raise AccessTokenError(f"Unsupported private segment: {segment}")
    if ttl_seconds <= 0:
        raise AccessTokenError("ttl_seconds must be positive")

    ts = int(time.time() if now is None else now)
    exp = _base36(ts + ttl_seconds)
    body = f"{TOKEN_VERSION}.{SEGMENT_TO_CODE[segment]}.{exp}"
    return f"{body}.{_sign(body, secret)}"


def verify_access_token(
    token: str,
    secret: str,
    *,
    now: int | None = None,
) -> str:
    parts = token.split(".")
    if len(parts) != 4:
        raise AccessTokenError("Invalid token format")

    version, code, exp_raw, sig = parts
    if version != TOKEN_VERSION:
        raise AccessTokenError("Unsupported token version")

    segment = CODE_TO_SEGMENT.get(code)
    if not segment:
        raise AccessTokenError("Unsupported token segment")

    body = f"{version}.{code}.{exp_raw}"
    expected = _sign(body, secret)
    if not hmac.compare_digest(sig, expected):
        raise AccessTokenError("Invalid token signature")

    ts = int(time.time() if now is None else now)
    if _from_base36(exp_raw) < ts:
        raise AccessTokenError("Token expired")

    return segment


def main() -> None:
    if len(sys.argv) not in {2, 3}:
        print(
            "Usage: python -m app.access_tokens SEGMENT [TTL_SECONDS]",
            file=sys.stderr,
        )
        raise SystemExit(2)

    secret = os.environ.get("PRIVATE_ACCESS_SECRET", "")
    if not secret:
        print("PRIVATE_ACCESS_SECRET is required", file=sys.stderr)
        raise SystemExit(2)

    ttl = int(sys.argv[2]) if len(sys.argv) == 3 else 600
    print(create_access_token(sys.argv[1], secret, ttl_seconds=ttl))


if __name__ == "__main__":
    main()
