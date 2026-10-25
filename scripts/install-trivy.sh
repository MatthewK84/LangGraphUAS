#!/usr/bin/env bash
# Install the one pinned trivy release into a directory (default $RUNNER_TEMP),
# verified against its published SHA-256 before it runs. This file holds the
# repo's only trivy pin: ci.yml (image scan) and sbom.yml (SBOM) both call it.
# A binary and a checksum, as for gitleaks, rather than a third-party action.
set -euo pipefail

TRIVY_VERSION="0.76.0"
TRIVY_SHA256="e24b1c51293c1b15e4ba8d45bbc7891ba053f90278ec2698f3562c993e145fe7"

dest="${1:-${RUNNER_TEMP:?pass a directory or set RUNNER_TEMP}}"
archive="trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"
curl -sSfL -o "$dest/$archive" \
  "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/${archive}"
echo "${TRIVY_SHA256}  $dest/$archive" | sha256sum --check --strict
tar -xzf "$dest/$archive" -C "$dest" trivy
"$dest/trivy" --version
