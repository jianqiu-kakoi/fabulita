#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  sudo ./scripts/install-host.sh \
    --domain english.chyuopen.com \
    [--email ops@example.com]

Installs Node.js 22, Caddy, SQLite tools, the myenglish system user,
systemd units, the Caddy site, and the backup timer on Ubuntu 24.04 or 26.04.
It does not deploy or start an application release.
USAGE
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

site_domain=""
acme_email=""
while (($#)); do
  case "$1" in
    --domain)
      (($# >= 2)) || die "--domain requires a value"
      site_domain="$2"
      shift 2
      ;;
    --email)
      (($# >= 2)) || die "--email requires a value"
      acme_email="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || die "run this script with sudo"
[[ "${site_domain}" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] ||
  die "invalid domain"
[[ "${site_domain}" == *.* ]] || die "domain must be a fully qualified name"
if [[ -n "${acme_email}" ]]; then
  [[ "${acme_email}" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] ||
    die "invalid ACME email"
fi

source /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] ||
  die "this installer requires Ubuntu; found ${PRETTY_NAME:-unknown OS}"
case "${VERSION_ID:-}" in
  24.04|26.04) ;;
  *)
    die "this installer targets Ubuntu 24.04 or 26.04; found ${PRETTY_NAME:-unknown OS}"
    ;;
esac

readonly ops_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly node_keyring="/etc/apt/keyrings/nodesource.gpg"
readonly caddy_keyring="/usr/share/keyrings/caddy-stable-archive-keyring.gpg"

temporary_files=()
cleanup() {
  local temporary_file
  for temporary_file in "${temporary_files[@]:-}"; do
    [[ -n "${temporary_file}" ]] && rm -f -- "${temporary_file}"
  done
}
trap cleanup EXIT

DEBIAN_FRONTEND=noninteractive apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  apt-transport-https \
  ca-certificates \
  curl \
  debian-archive-keyring \
  debian-keyring \
  gnupg \
  gzip \
  rsync \
  sqlite3 \
  ufw \
  unattended-upgrades

install -d -m 0755 /etc/apt/keyrings /usr/share/keyrings

node_key_tmp="$(mktemp)"
temporary_files+=("${node_key_tmp}")
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
  -o "${node_key_tmp}"
gpg --batch --yes --dearmor --output "${node_keyring}" "${node_key_tmp}"
chmod 0644 "${node_keyring}"
printf '%s\n' \
  "deb [arch=$(dpkg --print-architecture) signed-by=${node_keyring}] https://deb.nodesource.com/node_22.x nodistro main" \
  > /etc/apt/sources.list.d/nodesource.list

caddy_key_tmp="$(mktemp)"
temporary_files+=("${caddy_key_tmp}")
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
  -o "${caddy_key_tmp}"
gpg --batch --yes --dearmor --output "${caddy_keyring}" "${caddy_key_tmp}"
chmod 0644 "${caddy_keyring}"

caddy_source_tmp="$(mktemp)"
temporary_files+=("${caddy_source_tmp}")
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
  -o "${caddy_source_tmp}"
install -m 0644 "${caddy_source_tmp}" \
  /etc/apt/sources.list.d/caddy-stable.list

DEBIAN_FRONTEND=noninteractive apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs caddy

node -e '
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (major !== 22 || minor < 13) process.exit(1);
' || die "My English requires Node.js 22.13 or newer within the Node 22 line"

getent group myenglish >/dev/null ||
  groupadd --system myenglish
if ! id myenglish >/dev/null 2>&1; then
  useradd \
    --system \
    --gid myenglish \
    --home-dir /var/lib/my-english \
    --shell /usr/sbin/nologin \
    myenglish
fi

install -d -m 0755 -o root -g root \
  /opt/chyuopen \
  /opt/chyuopen/my-english \
  /opt/chyuopen/my-english/releases
install -d -m 0700 -o myenglish -g myenglish /var/lib/my-english
install -d -m 0750 -o root -g myenglish /etc/my-english
install -d -m 0700 -o root -g root /var/backups/my-english

if [[ ! -e /etc/my-english/my-english.env ]]; then
  install -m 0640 -o root -g myenglish \
    "${ops_dir}/env/my-english.env.example" \
    /etc/my-english/my-english.env
fi

install -m 0644 "${ops_dir}/systemd/my-english.service" \
  /etc/systemd/system/my-english.service
install -m 0644 "${ops_dir}/systemd/my-english-backup.service" \
  /etc/systemd/system/my-english-backup.service
install -m 0644 "${ops_dir}/systemd/my-english-backup.timer" \
  /etc/systemd/system/my-english-backup.timer
install -m 0755 "${ops_dir}/scripts/backup-sqlite.sh" \
  /usr/local/sbin/my-english-backup
install -d -m 0755 /etc/systemd/journald.conf.d
install -m 0644 "${ops_dir}/journald/90-my-english.conf" \
  /etc/systemd/journald.conf.d/90-my-english.conf

rendered_caddyfile="$(mktemp)"
temporary_files+=("${rendered_caddyfile}")
acme_email_directive=""
if [[ -n "${acme_email}" ]]; then
  acme_email_directive="email ${acme_email}"
fi
sed \
  -e "s/__SITE_DOMAIN__/${site_domain}/g" \
  -e "s/__ACME_EMAIL_DIRECTIVE__/${acme_email_directive}/g" \
  "${ops_dir}/caddy/Caddyfile.template" >"${rendered_caddyfile}"

if [[ -f /etc/caddy/Caddyfile ]] &&
   ! grep -q '^# Managed by My English VPS ops' /etc/caddy/Caddyfile; then
  install -m 0644 /etc/caddy/Caddyfile \
    "/etc/caddy/Caddyfile.pre-my-english.$(date -u +'%Y%m%dT%H%M%SZ')"
fi
install -m 0644 -o root -g root "${rendered_caddyfile}" /etc/caddy/Caddyfile
caddy fmt --overwrite /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile

systemctl daemon-reload
systemctl restart systemd-journald
systemctl enable my-english.service
systemctl enable --now my-english-backup.timer
systemctl enable --now caddy
systemctl reload caddy

cat <<EOF
Host preparation complete.

Next:
  1. sudoedit /etc/my-english/my-english.env
  2. Set ALLOWED_ORIGINS=https://${site_domain} and any LLM values.
  3. Deploy a release with scripts/deploy-release.sh.
  4. Apply ops/HARDENING.md only after verifying SSH key access.
EOF
