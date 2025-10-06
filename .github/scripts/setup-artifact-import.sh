#!/bin/bash
set -euxo pipefail

echo "Starting local registry so plan-integration can push images..."
docker run -d -p 32000:5000 --restart=always --name registry registry:2 || true
