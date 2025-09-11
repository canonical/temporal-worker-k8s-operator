#!/bin/bash
set -euo pipefail

echo "Initializing Vault..."

# Run the init action and capture the action ID
ACTION_ID=$(juju run-action vault-k8s/leader init --wait --format json | jq -r '.["action"]["id"]')

# Retrieve full action output
juju show-action-output "$ACTION_ID" --format json > vault-init.json

# Extract the first unseal key
KEY=$(jq -r '.["0"].results."unseal-keys"[0]' vault-init.json)

echo "Unsealing Vault..."
juju run-action vault-k8s/0 unseal key="$KEY" --wait

echo "Vault initialized and unsealed successfully."
