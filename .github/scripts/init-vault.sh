#!/bin/bash
set -euo pipefail

echo "Initializing Vault..."
juju run vault-k8s/leader init --wait > vault-init.json

# Grab the first unseal key using jq (already available on GitHub runners)
KEY=$(jq -r '.[].results."unseal-keys"[0]' vault-init.json)

echo "Unsealing Vault..."
juju run vault-k8s/0 unseal key="$KEY" --wait
