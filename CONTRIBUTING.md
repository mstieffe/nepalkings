# Contributing to Nepal Kings

Nepal Kings is proprietary software. Contributions require prior authorization
from the copyright holder and are accepted under the terms in [LICENSE](LICENSE).
This guide describes the engineering workflow for authorized contributors.

## Before changing code

1. Read the [development guide](docs/development.md) and
   [architecture overview](docs/architecture.md).
2. Start from `develop` unless a maintainer names another base branch.
3. Keep secrets, private player data, production logs, and local `.env` files
   out of commits and issue reports.
4. For security vulnerabilities, use the private process in
   [SECURITY.md](SECURITY.md), not a public issue.

## Change workflow

- Keep each change focused and preserve unrelated work in the tree.
- Put game legality and persistent state transitions on the server.
- Add a regression test at the boundary where a bug occurred.
- Update player, developer, or operational documentation with the behavior it
  describes; do not leave documentation cleanup for a later release.
- Treat files under `docs/plans/` as design records, not current runtime
  instructions. Current guides, tests, and code take precedence.

Run the standard local checks before requesting review:

```bash
.venv/bin/python scripts/check_markdown_links.py
.venv/bin/python -m pytest -q
```

Database or concurrency changes must also pass the PostgreSQL compatibility
job in GitHub Actions. Dependency and security changes must pass the repository
security workflow.

## Review checklist

- The change matches the issue or intended player behavior.
- New behavior has focused tests and the complete suite passes.
- User-facing text is accurate for the shipped rules.
- Configuration and deployment changes have safe defaults and updated runbooks.
- No credential, private data, generated build output, or local environment
  file is included.
- Local Markdown links pass `scripts/check_markdown_links.py`.

Maintainers merge release-ready work from `develop` into `main`. Tags matching
`v*` are reserved for versioned desktop releases.
