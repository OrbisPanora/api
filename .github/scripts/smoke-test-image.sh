#!/usr/bin/env bash
# Starts the container image and uploads one piece of a file through the chunked upload routes.
# This is the path that needs a writable upload folder, which the image has to provide.
#
#   .github/scripts/smoke-test-image.sh IMAGE
set -euo pipefail

image="${1:?usage: smoke-test-image.sh IMAGE}"
name="orbispanora-smoke-$$"
port="${SMOKE_PORT:-18000}"
base="http://127.0.0.1:$port"

cleanup() {
  docker logs "$name" 2>&1 | tail -30 || true
  docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d --name "$name" -p "127.0.0.1:$port:8000" "$image" >/dev/null
for _ in $(seq 1 60); do
  curl -sf "$base/api/worlds/health" >/dev/null && break
  sleep 1
done
curl -sf "$base/api/worlds/health" >/dev/null || { echo "The API did not start." >&2; exit 1; }

init="$(curl -sS -f -X POST "$base/api/upload/init" -F filename=smoke.zip -F total_chunks=1 -F total_size=10)"
upload_id="$(printf '%s' "$init" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["upload_id"])')"
head -c 10 /dev/zero > "${RUNNER_TEMP:-/tmp}/smoke-piece.bin"
curl -sS -f -X POST "$base/api/upload/chunk" -F "upload_id=$upload_id" -F chunk_index=0 \
  -F "chunk=@${RUNNER_TEMP:-/tmp}/smoke-piece.bin" >/dev/null
curl -sS -f -X DELETE "$base/api/upload/cancel/$upload_id" >/dev/null
echo "Smoke test passed: one piece was uploaded."
