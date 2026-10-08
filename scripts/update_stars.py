#!/usr/bin/env python3
"""Refresh star counts and ordering in the profile README.

The README stays the single source of truth; prose outside the sync blocks is
never touched. Inside each ``sync:`` block this script:

- fetches the current star count for every GitHub repository linked in a
  bullet,
- appends a one-significant-figure badge such as ``~300 ⭐`` (repositories
  with zero stars, unreachable repositories, and non-repository links get no
  badge),
- sorts the bullets by star count, highest first, keeping unbadged bullets in
  their original relative order at the end of the block.

Modes:
  update_stars.py           rewrite README.md in place
  update_stars.py --check   exit 1 when README.md is out of date

Authentication: uses the GITHUB_TOKEN environment variable when set. Without
it, unauthenticated GitHub API access (60 requests per hour) is enough for
this repository.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import urllib.request

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

BLOCK = re.compile(
    r"(<!-- sync:[a-z0-9-]+:start -->\n)(.*?)(<!-- sync:[a-z0-9-]+:end -->)",
    re.DOTALL,
)
GITHUB_REPO = re.compile(r"github\.com/([^/\s)]+)/([^/\s)#]+)")
BADGE = re.compile(r"\s*·\s~[\d.k]+\s⭐$")


def fetch_stars(full_name: str) -> int | None:
    url = f"https://api.github.com/repos/{full_name}"
    request = urllib.request.Request(url)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(json.load(response)["stargazers_count"])
    except Exception as error:
        print(f"warning: could not fetch {full_name}: {error}", file=sys.stderr)
        return None


def badge_for(stars: int) -> str:
    magnitude = 10 ** math.floor(math.log10(stars))
    approx = int(stars / magnitude + 0.5) * magnitude
    if approx >= 10_000:
        text = f"~{approx // 1000}k"
    else:
        text = f"~{approx}"
    return f" ·\u00a0{text}\u00a0⭐"


def render_line(line: str, stars: int | None) -> str:
    cleaned = BADGE.sub("", line.rstrip("\n"))
    if stars:
        cleaned += badge_for(stars)
    return cleaned + "\n"


def refresh_block(body: str) -> str:
    cache: dict[str, int | None] = {}
    parsed = []
    for index, line in enumerate(body.splitlines(keepends=True)):
        stars = None
        match = GITHUB_REPO.search(line)
        if match:
            full_name = f"{match.group(1)}/{match.group(2)}"
            if full_name not in cache:
                cache[full_name] = fetch_stars(full_name)
            stars = cache[full_name]
        parsed.append((index, line, stars))

    def order(item: tuple[int, str, int | None]) -> tuple[int, int, int]:
        index, _, stars = item
        if stars is None:
            return (1, 0, index)
        return (0, -stars, index)

    return "".join(render_line(line, stars) for _, line, stars in sorted(parsed, key=order))


def main() -> int:
    check = "--check" in sys.argv[1:]
    original = README.read_text()

    def replace(match: re.Match) -> str:
        return match.group(1) + refresh_block(match.group(2)) + match.group(3)

    updated = BLOCK.sub(replace, original)
    if updated == original:
        print("README.md is up to date")
        return 0
    if check:
        print("README.md is out of date; run scripts/update_stars.py", file=sys.stderr)
        return 1
    README.write_text(updated)
    print(f"updated {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
