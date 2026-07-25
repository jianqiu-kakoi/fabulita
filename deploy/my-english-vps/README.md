# My English independent VPS deployment

This directory contains the standalone deployment for
`https://english.chyuopen.com`:

- `frontend/`: static account shell, learner iframe, local-to-cloud sync
- `backend/`: Node 22 HTTP API with SQLite, sessions, sync, and LLM scoring
- `ops/`: Caddy, systemd, release/rollback, backup, and hardening files

It does not depend on CloudBase or OpenAI Sites. The browser talks only to the
same-origin `/api` endpoint; database and model credentials stay on the VPS.

## Local verification

```sh
(cd backend && npm ci --ignore-scripts && npm test)
(cd frontend && npm ci --ignore-scripts && npm run check)
bash -n ops/scripts/*.sh
git diff --check
```

## Release layout

The operations scripts accept a tarball with this layout:

```text
frontend/
  index.html
  privacy.html
  my-english.html
  assets/
server/
  package.json
  package-lock.json
  dist/
README.md
```

Build both projects, stage `frontend/dist/` as `frontend/`, and stage the
backend package files plus `backend/dist/` as `server/`. See
`ops/README.md` for host installation, deployment, rollback, and backup
commands.

## Invite beta registration gates

Before enabling invitation registration:

1. Keep the operator identity, contact route, unverified-email limitation,
   password-recovery limitation, and data-request process accurate in
   `frontend/privacy.html`.
2. Generate at least one unexpired one-time invite with the server-side CLI,
   then verify single use and concurrent registration before setting
   `REGISTRATION_ENABLED=true`.
3. Keep invite plaintext out of Git, logs, URLs, and public pages; revoke a
   leaked batch before issuing replacements.
4. If LLM scoring is enabled, name the provider, processing region, and privacy
   policy in the privacy notice first.
5. Add an A record for `english.chyuopen.com`, enable the Cloudflare proxy, and
   use Full (strict) TLS.
6. Verify registration, login, per-user data isolation, cross-device sync,
   logout, backup, and restore.
7. Keep password recovery clearly marked as unavailable during the invite beta.
