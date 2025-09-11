#!/bin/bash
set -euo pipefail

echo "Checking if Vault is already initialized..."
if juju run vault-k8s/leader is-initialized --format json | jq -e '.[].results.initialized' > /dev/null; then
  echo "Vault is already initialized. Skipping init."
else
  echo "Initializing Vault..."
  juju run vault-k8s/leader init --format json > vault-init.json

  # Grab the first unseal key
  KEY=$(jq -r '.[].results."unseal-keys"[0]' vault-init.json)

  echo "Unsealing Vault..."
  juju run vault-k8s/0 unseal key="$KEY" --format json
fi
