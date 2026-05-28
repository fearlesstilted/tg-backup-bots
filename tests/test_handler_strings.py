"""Regression guard: bot messages must not contain literal <...> tags.

Bots set parse_mode=HTML at the Bot level, so any user-facing string like
"Использование: /broadcast_status <id>" gets rejected by Telegram as an
unsupported HTML tag. This scan walks every string constant in handler
modules and fails if one looks like an HTML tag.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

HANDLERS_DIR = Path(__file__).resolve().parent.parent / "app" / "handlers"

# Matches <foo>, <foo_bar>, </id>, <segment > — anything that looks like a tag
# from Telegram's parser's point of view. Allows escaped &lt; / &gt; through.
_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z_][\w-]*\s*/?\s*>")


def _string_constants(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text())
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((node.lineno, node.value))
    return out


class HandlerStringTagScanTests(unittest.TestCase):
    def test_no_html_tagged_usage_strings(self) -> None:
        offenders: list[str] = []
        for path in sorted(HANDLERS_DIR.glob("*.py")):
            for lineno, text in _string_constants(path):
                if _TAG_RE.search(text):
                    offenders.append(f"{path.name}:{lineno}: {text!r}")
        self.assertFalse(
            offenders,
            msg=(
                "Found string literals containing <tag>-shaped substrings — "
                "these break with parse_mode=HTML. Rephrase or escape them:\n"
                + "\n".join(offenders)
            ),
        )


if __name__ == "__main__":
    unittest.main()
