#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage: sudo ./scripts/deploy-release.sh /path/to/my-english-release.tar.gz

The trusted release archive must contain:
  frontend/index.html
  server/package.json
  server/package-lock.json
  server/dist/server.js
USAGE
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

[[ $# -eq 1 ]] || {
  usage >&2
  exit 2
}
[[ "${EUID}" -eq 0 ]] || die "run this script with sudo"

release_archive="$(realpath -- "$1")"
[[ -f "${release_archive}" ]] || die "release archive not found"

readonly app_root="/opt/chyuopen/my-english"
readonly releases_dir="${app_root}/releases"
readonly current_link="${app_root}/current"
readonly previous_link="${app_root}/previous"
readonly next_link="${app_root}/.current.next"
readonly health_url="http://127.0.0.1:3000/api/health"
readonly release_sha="$(sha256sum "${release_archive}" | awk '{print $1}')"
readonly release_id="${release_sha:0:16}"
readonly release_dir="${releases_dir}/${release_id}"

install -d -m 0755 -o root -g root "${releases_dir}"
exec 9>/run/lock/my-english-deploy.lock
flock 9

if [[ -e "${release_dir}" ]]; then
  [[ -f "${release_dir}/.release-sha256" ]] ||
    die "existing release ${release_id} has no checksum marker"
  [[ "$(<"${release_dir}/.release-sha256")" == "${release_sha}" ]] ||
    die "existing release ${release_id} does not match the archive"
else
  while IFS= read -r archive_entry; do
    case "${archive_entry}" in
      /*|..|../*|*/../*|*/..)
        die "unsafe archive path: ${archive_entry}"
        ;;
    esac
  done < <(tar -tzf "${release_archive}")

  if LC_ALL=C tar -tvzf "${release_archive}" |
     awk 'substr($1, 1, 1) != "-" && substr($1, 1, 1) != "d" { found=1 } END { exit(found ? 0 : 1) }'; then
    die "release archive may contain only regular files and directories"
  fi

  staging_dir="$(mktemp -d "${releases_dir}/.staging.XXXXXX")"
  cleanup_staging() {
    [[ -n "${staging_dir:-}" && -d "${staging_dir}" ]] &&
      rm -rf -- "${staging_dir}"
    rm -f -- "${next_link}"
  }
  trap cleanup_staging EXIT

  tar -xzf "${release_archive}" \
    --no-same-owner \
    --no-same-permissions \
    -C "${staging_dir}"

  required_path=""
  for required_path in \
    frontend/index.html \
    server/package.json \
    server/package-lock.json \
    server/dist/server.js; do
    [[ -f "${staging_dir}/${required_path}" ]] ||
      die "release is missing ${required_path}"
  done

  chown -R myenglish:myenglish "${staging_dir}"
  runuser -u myenglish -- \
    env npm_config_cache=/var/lib/my-english/.npm-cache \
    npm --prefix "${staging_dir}/server" ci \
      --omit=dev \
      --ignore-scripts \
      --no-audit \
      --no-fund

  printf '%s\n' "${release_sha}" >"${staging_dir}/.release-sha256"
  chown -R root:root "${staging_dir}"
  chmod -R u=rwX,go=rX "${staging_dir}"
  mv -- "${staging_dir}" "${release_dir}"
  staging_dir=""
fi

previous_target=""
if [[ -L "${current_link}" ]]; then
  previous_target="$(readlink -f "${current_link}")"
elif [[ -e "${current_link}" ]]; then
  die "${current_link} must be a symlink"
fi

rm -f -- "${next_link}"
ln -s "${release_dir}" "${next_link}"
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
  printf 'New release failed its health check; restoring the prior release.\n' >&2
  if [[ -n "${previous_target}" && -d "${previous_target}" ]]; then
    rm -f -- "${next_link}"
    ln -s "${previous_target}" "${next_link}"
    mv -Tf -- "${next_link}" "${current_link}"
    systemctl restart my-english.service
  else
    systemctl stop my-english.service
    rm -f -- "${current_link}"
  fi
  exit 1
fi

if [[ -n "${previous_target}" && "${previous_target}" != "${release_dir}" ]]; then
  previous_next="${app_root}/.previous.next"
  rm -f -- "${previous_next}"
  ln -s "${previous_target}" "${previous_next}"
  mv -Tf -- "${previous_next}" "${previous_link}"
fi

printf 'Deployed release %s\n' "${release_id}"
printf 'Health check passed: %s\n' "${health_url}"
