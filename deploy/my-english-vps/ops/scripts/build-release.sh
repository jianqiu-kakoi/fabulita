#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf 'Usage: %s /absolute/path/to/my-english-release.tar.gz\n' "$0"
}

[[ $# -eq 1 ]] || {
  usage >&2
  exit 2
}

output_archive="$1"
[[ "${output_archive}" = /* ]] || {
  printf 'Output path must be absolute.\n' >&2
  exit 2
}

readonly deployment_root="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd
)"
readonly staging_dir="$(mktemp -d)"
cleanup() {
  rm -rf -- "${staging_dir}"
}
trap cleanup EXIT

(
  cd "${deployment_root}/backend"
  npm run build
)
(
  cd "${deployment_root}/frontend"
  npm run build
)

install -d \
  "${staging_dir}/frontend" \
  "${staging_dir}/server/dist"
cp -R "${deployment_root}/frontend/dist/." "${staging_dir}/frontend/"
install -m 0644 \
  "${deployment_root}/backend/package.json" \
  "${deployment_root}/backend/package-lock.json" \
  "${staging_dir}/server/"
cp -R "${deployment_root}/backend/dist/." "${staging_dir}/server/dist/"
install -m 0644 \
  "${deployment_root}/README.md" \
  "${staging_dir}/README.md"

mkdir -p -- "$(dirname -- "${output_archive}")"
tar -czf "${output_archive}" \
  -C "${staging_dir}" \
  frontend server README.md

printf 'Built release: %s\n' "${output_archive}"
