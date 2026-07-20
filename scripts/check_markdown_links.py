#!/usr/bin/env python3
"""Check that repository-local links in Markdown files resolve."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "artifacts",
    "backups",
    "build",
    "dist",
    "node_modules",
    "release",
}
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_SCHEMES = {"data", "ftp", "http", "https", "mailto", "tel"}


def markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory, names, filenames in os.walk(root):
        names[:] = sorted(name for name in names if name not in IGNORED_DIRECTORIES)
        base = Path(directory)
        files.extend(base / name for name in sorted(filenames) if name.endswith(".md"))
    return files


def link_destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def local_target(source: Path, destination: str) -> Path | None:
    if not destination or destination.startswith("#"):
        return None

    parsed = urlsplit(destination)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc:
        return None

    path_text = unquote(parsed.path)
    if not path_text or "{" in path_text or "}" in path_text:
        return None
    if path_text.startswith("/"):
        return REPO_ROOT / path_text.lstrip("/")
    return source.parent / path_text


def broken_links(path: Path) -> list[tuple[int, str]]:
    failures: list[tuple[int, str]] = []
    fence: str | None = None

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.lstrip()
        marker = stripped[:3]
        if marker in {"```", "~~~"}:
            fence = None if fence == marker else marker
            continue
        if fence:
            continue

        for match in LINK_PATTERN.finditer(line):
            destination = link_destination(match.group(1))
            target = local_target(path, destination)
            if target is not None and not target.exists():
                failures.append((line_number, destination))

    return failures


def main() -> int:
    failures: list[tuple[Path, int, str]] = []
    files = markdown_files(REPO_ROOT)
    for path in files:
        failures.extend((path, line, link) for line, link in broken_links(path))

    if failures:
        print("Broken local Markdown links:", file=sys.stderr)
        for path, line, link in failures:
            relative = path.relative_to(REPO_ROOT)
            print(f"  {relative}:{line}: {link}", file=sys.stderr)
        return 1

    print(f"Checked {len(files)} Markdown files; all local links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
