#!/bin/bash
set -euxo pipefail

# Allow plan-integration to fail later (we’ll import ourselves)
echo "Will manually import artifact into containerd after plan-integration"

# Find and import artifacts
ARTIFACT=$(find /tmp -name "temporal-worker_*.rock" | head -n1 || true)
if [ -n "$ARTIFACT" ]; then
  echo "Importing $ARTIFACT into Canonical k8s containerd..."
  sudo ctr -n k8s.io images import "$ARTIFACT"
fi
