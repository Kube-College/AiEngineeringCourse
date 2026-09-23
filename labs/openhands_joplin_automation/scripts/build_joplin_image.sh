#!/usr/bin/env bash
set -euo pipefail

LAB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${JOPLIN_SOURCE:-$LAB_ROOT/.data/joplin-source}"
BASE_SHA=1d6beb0443e6d958b2c241f45978bd5de069f309
BASE_IMAGE=ghcr.io/openhands/agent-server@sha256:44426bffabffa704b54a79cfeae71d0af5e702e80ef1b7276861307ecc9d598c
BUILD_CONTEXT="$LAB_ROOT/.data/joplin-build-context"
MANIFEST="$LAB_ROOT/docker/versions.json"
FORK=https://github.com/lspinheiro/joplin.git

mkdir -p "$LAB_ROOT/.data"
NEW_SOURCE=0
if [[ ! -d "$SOURCE/.git" ]]; then
  if [[ -e "$SOURCE" ]]; then
    echo "Joplin source path exists but is not a Git checkout" >&2
    exit 1
  fi
  git clone --filter=blob:none --no-checkout "$FORK" "$SOURCE"
  NEW_SOURCE=1
fi
if [[ "$(git -C "$SOURCE" remote get-url origin)" != "$FORK" ]]; then
  echo "Joplin source is not the configured fork" >&2
  exit 1
fi
if [[ "$NEW_SOURCE" -eq 0 && -n "$(git -C "$SOURCE" status --porcelain)" ]]; then
  echo "Joplin source checkout has local changes" >&2
  exit 1
fi
if ! git -C "$SOURCE" cat-file -e "$BASE_SHA^{commit}" 2>/dev/null; then
  git -C "$SOURCE" fetch origin "$BASE_SHA"
fi
if [[ "$(git -C "$SOURCE" rev-parse HEAD)" != "$BASE_SHA" ]]; then
  git -C "$SOURCE" checkout --detach "$BASE_SHA"
fi
if [[ -n "$(git -C "$SOURCE" status --porcelain)" ]]; then
  echo "Joplin source checkout has local changes" >&2
  exit 1
fi
docker image inspect "$BASE_IMAGE" >/dev/null
mkdir -p "$BUILD_CONTEXT"
find "$BUILD_CONTEXT" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
git -C "$SOURCE" archive --format=tar "$BASE_SHA" | tar -xf - -C "$BUILD_CONTEXT"
# The upstream .dockerignore excludes app-desktop and other Yarn workspaces.
# This archive is already limited to tracked public files at BASE_SHA.
printf '.git/\n**/node_modules/\n.yarn/cache/\n' > "$BUILD_CONTEXT/.dockerignore"

if [[ "${JOPLIN_SKIP_BUILD:-0}" != "1" ]]; then
  docker build --platform linux/arm64 \
    --file "$LAB_ROOT/docker/joplin-agent.Dockerfile" \
    --tag openhands-joplin-agent:1d6beb0 "$BUILD_CONTEXT"
else
  : "${JOPLIN_EXPECTED_IMAGE_ID:?Set the inspected image ID when using a prebuilt archive}"
fi

IMAGE_ID="$(docker image inspect openhands-joplin-agent:1d6beb0 --format '{{.Id}}')"
if [[ "${JOPLIN_SKIP_BUILD:-0}" == "1" && "$IMAGE_ID" != "$JOPLIN_EXPECTED_IMAGE_ID" ]]; then
  echo "Loaded image does not match the expected image ID" >&2
  exit 1
fi
SOURCE_LOCK_SHA="$(shasum -a 256 "$SOURCE/yarn.lock" | cut -d ' ' -f 1)"
IMAGE_LOCK_SHA="$(docker run --rm --entrypoint /bin/sh openhands-joplin-agent:1d6beb0 -c 'sha256sum /opt/joplin/yarn.lock' | cut -d ' ' -f 1)"
if [[ "$IMAGE_LOCK_SHA" != "$SOURCE_LOCK_SHA" ]]; then
  echo "Built image changed the pinned Joplin lockfile" >&2
  exit 1
fi
SOURCE_PACKAGE_SHA="$(shasum -a 256 "$SOURCE/package.json" | cut -d ' ' -f 1)"
IMAGE_PACKAGE_SHA="$(docker run --rm --entrypoint /bin/sh openhands-joplin-agent:1d6beb0 -c 'sha256sum /opt/joplin/package.json' | cut -d ' ' -f 1)"
if [[ "$IMAGE_PACKAGE_SHA" != "$SOURCE_PACKAGE_SHA" ]]; then
  echo "Built image did not restore the pinned Joplin package manifest" >&2
  exit 1
fi
VERSIONS="$(docker run --rm --entrypoint /bin/sh openhands-joplin-agent:1d6beb0 -c 'python3 --version; node --version; node /opt/joplin/.yarn/releases/yarn-4.16.0.cjs --version')"
cd "$LAB_ROOT"
uv run --no-sync python - "$MANIFEST" "$BASE_SHA" "$BASE_IMAGE" "$IMAGE_ID" "$VERSIONS" <<'PY'
import json
import os
import sys
from pathlib import Path

manifest, source_sha, base_image, image_id, versions = sys.argv[1:]
python_version, node_version, yarn_version = versions.splitlines()
if yarn_version != '4.16.0' or not image_id.startswith('sha256:'):
    raise SystemExit('Built image did not report the pinned toolchain')
result = {
    'joplin_sha': source_sha,
    'agent_server_version': '1.48.0',
    'base_image_digest': base_image,
    'python_version': python_version.removeprefix('Python '),
    'node_version': node_version.removeprefix('v'),
    'package_manager': f'yarn@{yarn_version}',
    'built_image_digest': image_id,
}
target = Path(manifest)
temporary = target.with_suffix('.json.tmp')
temporary.write_text(json.dumps(result, indent=2) + '\n')
os.replace(temporary, target)
PY
