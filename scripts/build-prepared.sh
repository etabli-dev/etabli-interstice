#!/bin/sh
# Copyright 2026 R. Heller
# SPDX-License-Identifier: AGPL-3.0-only
set -eu
: "${TMPDIR:?Set TMPDIR to a private build workspace}"
: "${INTERSTICE_PYTHON:?Set INTERSTICE_PYTHON to a Python 3.13 executable}"
build_context=$(mktemp -d "$TMPDIR/interstice-build.XXXXXX")
trap 'rm -rf "$build_context"' EXIT HUP INT TERM
uv pip install --python "$INTERSTICE_PYTHON" --target "$build_context/vendor" --require-hashes --only-binary :all: -r requirements.lock
cp -R app "$build_context/app"
cp LICENSE NOTICE requirements.lock "$build_context/"
cp deploy/Dockerfile.prepared "$build_context/Dockerfile"
docker build --build-arg "REVISION=${REVISION:-development}" -t "${INTERSTICE_IMAGE:-etabli-interstice:0.1.0-test}" "$build_context"
