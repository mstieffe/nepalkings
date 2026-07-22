# Nepal Kings agent guide

Work from the repository root and use `.venv/bin/python` for local Python
commands. Preserve unrelated user changes and keep `develop` and `main`
distinct: `develop` is the server/integration branch, while `main` publishes
the browser client through GitHub Pages.

## EU server deployment

Read [docs/deployment.md](docs/deployment.md) first. The authoritative
provider paths, environment IDs, recovery behavior, and manual details are in
[deploy/pythonanywhere/README.md](deploy/pythonanywhere/README.md).

The supported paid EU staging/production entrypoint is:

```bash
.venv/bin/python scripts/deploy_pythonanywhere_eu.py \
  --environment both \
  --push \
  --execute \
  --confirm-sha "$(git rev-parse HEAD)" \
  --allow-missing-authenticated-read
```

Run the command without `--execute` first for its read-only plan. Prefer
owner-only `--smoke-credentials ENV=/private/file.json` inputs over the
authenticated-read waiver when maintained smoke accounts are available. Add
`--conquer-smoke-staging` for releases that require the deliberate,
data-retaining Conquer smoke.

Do not use `deploy_server.sh` for the paid EU environments; it targets the
legacy mutable US/SQLite layout. Do not deploy production alone unless an
incident explicitly requires it and the command includes
`--production-without-staging`. The orchestrator is fail-closed: investigate
and recover the reported environment before bypassing a gate.

The server deploy does not publish client assets. Browser/mobile-web changes
still require the reviewed `develop` to `main` promotion described in
[docs/deployment.md](docs/deployment.md#browser-publication).
