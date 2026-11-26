#!/bin/sh
# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
set -eu
image=${1:?Specify the image to check}
: "${RUNNER_TEMP:=${TMPDIR:?Set a private temporary directory}}"
work=$(mktemp -d "$RUNNER_TEMP/interstice-container.XXXXXX")
name=interstice-check-$$
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; sudo rm -rf "$work"; }
trap cleanup EXIT HUP INT TERM
mkdir "$work/data"
printf '%s' '[{"id":"ci","role":"admin","token":"isolated-ci-only-not-a-real-credential"}]' > "$work/tokens.json"
sudo chown -R 10005:10005 "$work"
sudo chmod 700 "$work/data"
sudo chmod 400 "$work/tokens.json"
docker run -d --name "$name" --read-only --user 10005:10005 --network none \
  --cpus 1 --memory 512m --pids-limit 80 --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,size=32m -v "$work/data:/data" -v "$work/tokens.json:/run/secrets/tokens.json:ro" "$image"
ready=0
for attempt in $(seq 1 30); do
  if docker exec "$name" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=2)" >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
[ "$ready" = 1 ] || { docker logs "$name"; exit 1; }
# A second server must fail before binding a port or opening the task database.
if failure=$(docker exec "$name" python -m app.serve 2>&1); then exit 1; fi
case "$failure" in *"Another server owns this data directory"*) ;; *) printf '%s\n' "$failure"; exit 1;; esac
docker exec "$name" python -m app.manage backup /data/interstice.sqlite /data/backup.sqlite
docker exec "$name" python -m app.manage restore /data/backup.sqlite /data/restored/interstice.sqlite
