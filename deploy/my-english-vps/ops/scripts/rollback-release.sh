#!/usr/bin/env bash
set -Eeuo pipefail

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

[[ $# -le 1 ]] || die "usage: sudo $0 [release-id]"
[[ "${EUID}" -eq 0 ]] || die "run this script with sudo"

readonly app_root="/opt/chyuopen/my-english"
readonly releases_dir="${app_root}/releases"
readonly current_link="${app_root}/current"
readonly previous_link="${app_root}/previous"
readonly next_link="${app_root}/.current.next"
readonly health_url="http://127.0.0.1:3000/api/health"
readonly environment_file="/etc/my-english/my-english.env"

exec 9>/run/lock/my-english-deploy.lock
flock 9

if [[ $# -eq 1 ]]; then
  [[ "$1" =~ ^[a-f0-9]{16}$ ]] || die "release-id must be 16 lowercase hex characters"
  target_release="${releases_dir}/$1"
else
  [[ -L "${previous_link}" ]] || die "no previous release is recorded"
  target_release="$(readlink -f "${previous_link}")"
fi

case "${target_release}" in
  "${releases_dir}/"*) ;;
  *) die "rollback target is outside the releases directory" ;;
esac
[[ -d "${target_release}" && -f "${target_release}/.release-sha256" ]] ||
  die "rollback target is not a valid release"
[[ -f "${environment_file}" ]] ||
  die "application environment file is missing"

old_target=""
[[ -L "${current_link}" ]] && old_target="$(readlink -f "${current_link}")"
[[ -n "${old_target}" ]] || die "there is no active release"
[[ "${old_target}" != "${target_release}" ]] || die "target release is already active"

# A prior release may predate mandatory email verification. Always close
# registration before changing code so a rollback can never reopen the old
# unverified registration path. Reopening is a separate, deliberate operation.
grep -Eq '^REGISTRATION_ENABLED=(true|false)$' "${environment_file}" ||
  die "REGISTRATION_ENABLED must be an exact true/false entry before rollback"
if grep -Eq '^REGISTRATION_ENABLED=true$' "${environment_file}"; then
  sed -i 's/^REGISTRATION_ENABLED=true$/REGISTRATION_ENABLED=false/' \
    "${environment_file}"
  printf '%s\n' \
    'Registration was open and has been closed before rollback.' >&2
fi

rm -f -- "${next_link}"
ln -s "${target_release}" "${next_link}"
mv -Tf -- "${next_link}" "${current_link}"

healthy="false"
if systemctl restart my-english.service; then
  for _attempt in {1..20}; do
    if curl --fail --silent --max-time 2 "${health_url}" >/dev/null; then
      healthy="true"
      break
    fi
    sleep 1
  done
fi

if [[ "${healthy}" != "true" ]]; then
  printf 'Rollback target failed health check; restoring active release.\n' >&2
  rm -f -- "${next_link}"
  ln -s "${old_target}" "${next_link}"
  mv -Tf -- "${next_link}" "${current_link}"
  systemctl restart my-english.service
  exit 1
fi

previous_next="${app_root}/.previous.next"
rm -f -- "${previous_next}"
ln -s "${old_target}" "${previous_next}"
mv -Tf -- "${previous_next}" "${previous_link}"

printf 'Rolled back to %s\n' "$(basename "${target_release}")"
