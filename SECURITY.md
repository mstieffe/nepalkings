# Security policy

## Reporting a vulnerability

If you believe you have found a security vulnerability in nepalkings,
please **do not open a public issue**. Instead email the maintainer at
the address in `LICENSE` / `pyproject` metadata with:

- a description of the issue,
- steps to reproduce,
- the affected commit / version,
- any proof-of-concept you may have.

You will receive an acknowledgement and a coordinated disclosure plan.

## Supported versions

Only the `main` branch is actively patched. Tagged releases are
best-effort.

## Secret handling

- Secrets (API keys, SMTP credentials, the Flask `SECRET_KEY`) MUST be
  provided via environment variables. The repository contains no real
  secrets; `.env` is gitignored and `.env.example` documents the keys.
- The server refuses to boot in any non-development environment if
  `SECRET_KEY` is not set explicitly — see `server/server.py`.
- `DROP_TABLES_ON_STARTUP` defaults to `False`. The server refuses to
  boot in non-development environments if this is set to `True`.
- `CORS_ORIGINS` defaults to a locked-down localhost list. Wide-open
  `*` must be set explicitly.

## What is in scope

- Authentication & session token issuance / validation.
- Rate-limited routes and abuse protection.
- Battle / kingdom state mutations through HTTP routes.
- Build / deploy scripts that rsync to production.

## What is not in scope

- Issues that require local code execution as the user already running
  the client.
- Asset-pipeline scripts under `scripts/assets/` (they are dev tools
  and never invoked by the runtime).
