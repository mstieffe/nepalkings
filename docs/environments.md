# Environments and Client Routing

Last verified: 2026-07-20

This is the authoritative guide for choosing a Nepal Kings backend. Use the
live `/healthz` and `/readyz` responses to verify release and schema state;
dated deployment details belong in the
[production launch record](operations/PRODUCTION_DEPLOYMENT_2026-07-19.md).

## Environment matrix

| Environment | API URL | Data | Intended use |
|---|---|---|---|
| Local | `http://localhost:5000` | Local SQLite database | Development and tests |
| EU staging | `https://nepalkingz.eu.pythonanywhere.com` | Isolated staging PostgreSQL | Integration, migration, load, and release-candidate checks |
| EU production | `https://api-nepalkingz.eu.pythonanywhere.com` | Isolated production PostgreSQL | Public beta |
| Legacy fallback | `https://nepalkings.pythonanywhere.com` | Historical development data | Emergency free-plan fallback only |

Staging and production do not share a database, database role, signing key,
private environment file, web app, or background worker. Accounts, tokens,
games, collections, kingdoms, and land ownership created in one environment do
not exist in another.

The legacy service is not a replica or recovery copy of production. Its
matching code is retained on `backup/pythonanywhere-free-eu-2026-07-19`; using
that branch is an infrastructure fallback with separate historical data.

## Published client default

The public GitHub Pages client, current source checkout, remote-run helper, and
new desktop builds default to:

```text
https://api-nepalkingz.eu.pythonanywhere.com
```

Production routing is defined in:

- `nepal_kings/main.py`;
- `nepal_kings/config/server_settings.py`;
- `run_remote.sh`;
- `build_installer.sh`;
- `.github/workflows/build.yml`.

Changing a backend environment file does not redirect released clients. The
browser default changes only after a new `main` build reaches GitHub Pages;
desktop defaults change only in newly built packages. Keep an older API
hostname working during any supported client-upgrade window.

## Use an environment

### Local development

```bash
./run_local.sh
```

The helper starts the local API and passes `http://localhost:5000` explicitly
to the client.

### Production source client

```bash
./run_remote.sh
```

This is the normal hosted smoke path and uses the production default.

### Staging source client

```bash
cd nepal_kings
../.venv/bin/python main.py \
  --server-url https://nepalkingz.eu.pythonanywhere.com
```

Use a staging-only account. Do not expect a production login to work.

### Staging browser client

Use the explicit query override on the published web build:

```text
https://mstieffe.github.io/nepalkings/?server_url=https%3A%2F%2Fnepalkingz.eu.pythonanywhere.com
```

Close other Nepal Kings tabs before testing a different environment so an old
tab does not continue polling with another account or server choice.

### Desktop routing precedence

The desktop client chooses its API in this order:

1. `--server-url` command-line option;
2. `SERVER_URL` environment variable;
3. saved choice in `~/.nepalkings/resolution.json`;
4. baked-in production default.

An explicit staging choice can therefore persist across launches. Re-select
production in Settings or pass the production URL to switch back.

## Hosted deployment boundaries

Paid EU staging and production use immutable release directories, PostgreSQL
backups, explicit `manage.py prepare-database`, WSGI-only web workers, and one
dedicated always-on worker per environment. Follow the
[PythonAnywhere runbook](../deploy/pythonanywhere/README.md).

Do not use `deploy_server.sh` for the paid EU environments. It belongs to the
legacy mutable-directory/SQLite deployment shape and defaults to the old
account.

Before promoting a release, confirm:

- staging and production point to their intended private environment files;
- `/healthz` reports the intended environment and release;
- `/readyz` reports the expected database and schema;
- the background worker holds exactly one environment-specific leadership lock;
- browser CORS allows the exact published origin, without a path;
- registration, authentication, Collection, Conquest configuration, and the
  kingdom map pass the required smoke checks.

## Custom domains later

Adding branded web and API domains does not require recreating PostgreSQL.
Configure the new hostnames on the existing services, update API and CORS
configuration, verify TLS and gameplay, then publish newly routed clients.

Keep the PythonAnywhere hostname available while older desktop packages still
use it. See [distribution.md](distribution.md) for client release boundaries
and [deployment.md](deployment.md) for promotion and rollback.
