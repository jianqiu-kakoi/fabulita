# My English single-VPS operations

Target: Ubuntu 24.04 or 26.04, Node.js 22.13+, Caddy, systemd, and SQLite.

```text
Cloudflare -> Caddy :443
                  |-> static /opt/chyuopen/my-english/current/frontend
                  `-> /api -> 127.0.0.1:3000

systemd my-english -> /opt/chyuopen/my-english/current/server/dist/server.js
SQLite             -> /var/lib/my-english/my-english.sqlite
secrets/env         -> /etc/my-english/my-english.env
daily backups       -> /var/backups/my-english
```

No script in this directory contains a credential. The environment example
contains blank placeholders only.

## 1. Release contract

Build on a trusted development or CI machine. Do not compile TypeScript as
root on the VPS. The `.tar.gz` root must be:

```text
frontend/
  index.html
  privacy.html
  my-english.html
  assets/...
server/
  package.json
  package-lock.json
  dist/
    server.js
```

The deployer installs production dependencies with lifecycle scripts disabled.
The current backend uses only Node 22 built-ins, including `node:sqlite`.

From the repository, build that archive with:

```sh
./deploy/my-english-vps/ops/scripts/build-release.sh \
  /tmp/my-english-release.tar.gz
```

## 2. Prepare the host

Copy this `ops` directory to the VPS, then:

```sh
cd /path/to/ops
sudo ./scripts/install-host.sh \
  --domain english.chyuopen.com
sudoedit /etc/my-english/my-english.env
```

`--email YOUR_REAL_ACME_EMAIL` is optional. It sets the ACME account contact
used by Caddy but is not required for certificate issuance.

Keep these exact network values:

```text
HOST=127.0.0.1
PORT=3000
ALLOWED_ORIGINS=https://english.chyuopen.com
DATABASE_PATH=/var/lib/my-english/my-english.sqlite
```

Add the LLM provider values only in `/etc/my-english/my-english.env`. Then:

```sh
sudo chown root:myenglish /etc/my-english/my-english.env
sudo chmod 0640 /etc/my-english/my-english.env
sudo systemctl restart caddy
```

### Registration and password-work gate

The production environment example deliberately contains:

```text
REGISTRATION_ENABLED=false
PASSWORD_SCRYPT_CONCURRENCY=2
PASSWORD_SCRYPT_QUEUE_LIMIT=8
```

Leave registration closed through the first deployment. The health response
must report `"registrationEnabled": false` and
`"privacyConsentVersion": "2026-07-25"`. Before changing the flag to `true`,
verify that the public privacy notice is the matching version and that the
registration client sends:

```json
{
  "privacyConsent": {
    "accepted": true,
    "version": "2026-07-25"
  }
}
```

After deliberately opening registration, restart `my-english` and recheck the
health response. Do not raise password concurrency above two on the 1.6 GB
VPS. Each current scrypt operation uses roughly 128 MiB, and the backend also
clamps this setting to two.

At Cloudflare, point `english.chyuopen.com` to the VPS, enable the orange cloud,
and select **Full (strict)** TLS. Do not enable Rocket Loader or third-party
browser scripts without revisiting the Content Security Policy.

### Client IP and request limits

The Caddy template trusts `CF-Connecting-IP`/`X-Forwarded-For` only when the
immediate TCP peer belongs to Cloudflare's published IPv4 or IPv6 ranges, and
uses strict right-to-left proxy parsing. Direct requests to the public origin
keep their actual source IP; caller-supplied proxy headers are not trusted.
Caddy then replaces the upstream `X-Forwarded-For` value with that validated
single IP and removes `CF-Connecting-IP` before proxying. This lets the
backend's authentication limiter operate per client rather than grouping users
under one Cloudflare edge IP or accepting a spoofed header chain.

Cloudflare can change these ranges. Before a Caddy upgrade and at least
quarterly, compare the template's `trusted_proxies` line with:

- <https://www.cloudflare.com/ips-v4>
- <https://www.cloudflare.com/ips-v6>

Validate and reload after updating it:

```sh
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy accepts API request bodies up to 2 MB, intentionally above the backend's
1 MiB sync contract and 1.1 MB transport ceiling. The backend remains the
authoritative size check.

## 3. Deploy

```sh
sudo ./scripts/deploy-release.sh /path/to/my-english-release.tar.gz
curl --fail https://english.chyuopen.com/api/health
```

The archive SHA-256 becomes the immutable release ID. Deployment switches the
`current` symlink atomically, restarts the API, checks localhost health for up
to 20 seconds, and restores the prior release automatically if health fails.

Inspect:

```sh
sudo systemctl status my-english --no-pager
sudo journalctl -u my-english -n 100 --no-pager
sudo caddy validate --config /etc/caddy/Caddyfile
```

## 4. Roll back

List immutable releases and the recorded prior release:

```sh
ls -1 /opt/chyuopen/my-english/releases
readlink -f /opt/chyuopen/my-english/previous
```

Roll back to the recorded prior release:

```sh
sudo ./scripts/rollback-release.sh
```

Or select a 16-character release ID:

```sh
sudo ./scripts/rollback-release.sh RELEASE_ID
```

Rollback also performs a health check and restores the previously active
release if the selected target is unhealthy.

## 5. Backups

The timer creates a transactionally consistent SQLite backup every day, checks
`PRAGMA integrity_check`, compresses it, and writes a SHA-256 sidecar. Local
retention is 14 days.

```sh
sudo systemctl list-timers my-english-backup.timer
sudo systemctl start my-english-backup.service
sudo journalctl -u my-english-backup -n 50 --no-pager
sudo ls -l /var/backups/my-english
```

Before a manual restore, stop the API and make one final copy. Verify the chosen
backup with its `.sha256` sidecar and run `PRAGMA integrity_check` again before
installing it as the live database. Keep at least one encrypted offsite copy;
the local timer is not protection from deletion of the entire VPS.

## 6. Logs

Both Caddy and the API write to journald; no application log files need
logrotate. The installer caps persistent logs at 500 MB, runtime-only logs at
100 MB, and retention at 14 days.

```sh
sudo journalctl -u my-english -f
sudo journalctl -u caddy -f
sudo journalctl --disk-usage
```

Complete [HARDENING.md](HARDENING.md) only after key-only SSH access has been
verified from a second session.
