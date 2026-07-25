#!/usr/bin/env bash
set -Eeuo pipefail

readonly database_path="/var/lib/my-english/my-english.sqlite"
readonly backup_dir="/var/backups/my-english"
readonly retention_days="14"
readonly lock_path="/run/my-english-backup/backup.lock"

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Run as root: sudo %s\n' "$0" >&2
  exit 1
fi

install -d -m 0700 -o root -g root "${backup_dir}"
exec 9>"${lock_path}"
flock -n 9 || {
  printf 'Another My English backup is already running.\n' >&2
  exit 0
}

if [[ ! -f "${database_path}" ]]; then
  printf 'No database yet at %s; nothing to back up.\n' "${database_path}"
  exit 0
fi

timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
snapshot_path="$(mktemp "${backup_dir}/.snapshot.XXXXXX")"
compressed_path="$(mktemp "${backup_dir}/.compressed.XXXXXX")"
final_path="${backup_dir}/my-english-${timestamp}.sqlite.gz"

cleanup() {
  rm -f -- "${snapshot_path}" "${compressed_path}"
}
trap cleanup EXIT

sqlite3 "${database_path}" \
  ".timeout 10000" \
  ".backup '${snapshot_path}'"

integrity_result="$(sqlite3 "${snapshot_path}" 'PRAGMA integrity_check;')"
if [[ "${integrity_result}" != "ok" ]]; then
  printf 'Backup integrity check failed: %s\n' "${integrity_result}" >&2
  exit 1
fi

gzip -9 -n --stdout "${snapshot_path}" >"${compressed_path}"
chmod 0600 "${compressed_path}"
mv -- "${compressed_path}" "${final_path}"

(
  cd "${backup_dir}"
  sha256sum "$(basename "${final_path}")" >"$(basename "${final_path}").sha256"
  chmod 0600 "$(basename "${final_path}").sha256"
)

find "${backup_dir}" -maxdepth 1 -type f \
  \( -name 'my-english-*.sqlite.gz' -o -name 'my-english-*.sqlite.gz.sha256' \) \
  -mtime "+${retention_days}" -delete

printf 'Created verified backup: %s\n' "${final_path}"
