#!/bin/sh
# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
set -eu
image=${1:?Specify the image}
output=${2:?Specify an evidence directory}
: "${RUNNER_TEMP:=${TMPDIR:?Set a private temporary directory}}"
work=$(mktemp -d "$RUNNER_TEMP/interstice-audit.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
curl -fsSL --max-time 120 https://github.com/aquasecurity/trivy/releases/download/v0.76.2/trivy_0.76.2_Linux-64bit.tar.gz -o "$work/trivy.tar.gz"
printf '%s  %s\n' bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf "$work/trivy.tar.gz" | sha256sum -c -
tar -xzf "$work/trivy.tar.gz" -C "$work" trivy
mkdir -p "$output"
export GOMAXPROCS=1
"$work/trivy" image --parallel 1 --scanners vuln --cache-dir "$work/cache" --format json --output "$output/vulnerabilities.json" "$image"
"$work/trivy" image --parallel 1 --cache-dir "$work/cache" --format cyclonedx --output "$output/sbom.json" "$image"
python - "$output/vulnerabilities.json" <<'PY'
import json,sys
report=json.load(open(sys.argv[1]))
findings=[v for group in report.get('Results',[]) for v in group.get('Vulnerabilities',[])]
fixable=[v for v in findings if v.get('FixedVersion') and v['Severity'] in ('HIGH','CRITICAL')]
print(json.dumps({'findings':len(findings),'fixable_high_critical':[{k:v.get(k) for k in ('VulnerabilityID','PkgName','FixedVersion')} for v in fixable]}))
if fixable:raise SystemExit(1)
PY
