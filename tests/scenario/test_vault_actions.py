# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the vault action handlers: add-vault-secret and get-vault-secret.

All tests run the action through ops.testing.Context (Scenario) so the full
ops framework is exercised. When a handler calls event.fail(), context.run
raises ops.testing.ActionFailed carrying the failure message; successful runs
populate context.action_results.
"""

import unittest.mock

import ops.testing
import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

VAULT_CLIENT = "relations.vault.VaultRelation.get_vault_client"


@pytest.fixture
def base_state(temporal_worker_container, vault_relation, peer_relation, config, vault_nonce_secret):
    """Minimal state with a connected container, vault relation, and peer relation."""
    return ops.testing.State(
        containers=[temporal_worker_container],
        relations=[vault_relation, peer_relation],
        config=config,
        secrets=[vault_nonce_secret],
    )


@pytest.fixture
def disconnected_state(vault_relation, peer_relation, config, vault_nonce_secret):
    """State where the workload container cannot be connected to."""
    return ops.testing.State(
        containers=[ops.testing.Container("temporal-worker", can_connect=False)],
        relations=[vault_relation, peer_relation],
        config=config,
        secrets=[vault_nonce_secret],
    )


# ── add-vault-secret ──────────────────────────────────────────────────────────


def test_add_vault_secret_fails_if_validation_fails(context, disconnected_state):
    """Action fails and does not proceed when the workload container is unreachable."""
    with unittest.mock.patch(VAULT_CLIENT) as get_vault_client:
        with pytest.raises(ops.testing.ActionFailed) as excinfo:
            context.run(
                context.on.action("add-vault-secret", params={"path": "p", "key": "k", "value": "v"}),
                disconnected_state,
            )

    assert excinfo.value.message == "Failed to connect to the container"
    get_vault_client.assert_not_called()


def test_add_vault_secret_fails_if_params_missing(context, base_state):
    """Action fails and does not reach the vault client when required params are absent."""
    with unittest.mock.patch(VAULT_CLIENT) as get_vault_client:
        with pytest.raises(ops.testing.ActionFailed) as excinfo:
            context.run(
                context.on.action("add-vault-secret", params={"path": "p"}),  # key and value missing
                base_state,
            )

    assert excinfo.value.message == "`path`, `key` and `value` are required parameters"
    get_vault_client.assert_not_called()


def test_add_vault_secret_fails_if_vault_client_unavailable(context, base_state):
    """Action fails and does not attempt a write when the vault client cannot be created."""
    with unittest.mock.patch(VAULT_CLIENT, side_effect=Exception("vault unreachable")) as get_vault_client:
        with pytest.raises(ops.testing.ActionFailed) as excinfo:
            context.run(
                context.on.action("add-vault-secret", params={"path": "p", "key": "k", "value": "v"}),
                base_state,
            )

    assert excinfo.value.message == "Unable to initialize vault client. remove relation and retry."
    get_vault_client.assert_called_once()


def test_add_vault_secret_succeeds(context, base_state):
    """Action writes the secret and returns a success result when all conditions are met."""
    mock_client = unittest.mock.Mock()
    with unittest.mock.patch(VAULT_CLIENT, return_value=mock_client):
        context.run(
            context.on.action("add-vault-secret", params={"path": "p", "key": "k", "value": "v"}),
            base_state,
        )
    assert context.action_results == {"result": "secret successfully created"}
    mock_client.write_secret.assert_called_once_with(path="p", key="k", value="v")


# ── get-vault-secret ──────────────────────────────────────────────────────────


def test_get_vault_secret_fails_if_validation_fails(context, disconnected_state):
    """Action fails and does not proceed when the workload container is unreachable."""
    with unittest.mock.patch(VAULT_CLIENT) as get_vault_client:
        with pytest.raises(ops.testing.ActionFailed) as excinfo:
            context.run(
                context.on.action("get-vault-secret", params={"path": "p", "key": "k"}),
                disconnected_state,
            )

    assert excinfo.value.message == "Failed to connect to the container"
    get_vault_client.assert_not_called()


def test_get_vault_secret_fails_if_params_missing(context, base_state):
    """Action fails and does not reach the vault client when required params are absent."""
    with unittest.mock.patch(VAULT_CLIENT) as get_vault_client:
        with pytest.raises(ops.testing.ActionFailed) as excinfo:
            context.run(
                context.on.action("get-vault-secret", params={"path": "p"}),  # key missing
                base_state,
            )

    assert excinfo.value.message == "`path` and `key` are required parameters"
    get_vault_client.assert_not_called()


def test_get_vault_secret_fails_if_vault_client_unavailable(context, base_state):
    """Action fails and does not attempt a read when the vault client cannot be created."""
    with unittest.mock.patch(VAULT_CLIENT, side_effect=Exception("vault unreachable")) as get_vault_client:
        with pytest.raises(ops.testing.ActionFailed) as excinfo:
            context.run(
                context.on.action("get-vault-secret", params={"path": "p", "key": "k"}),
                base_state,
            )

    assert excinfo.value.message == "Unable to initialize vault client. Remove relation and retry."
    get_vault_client.assert_called_once()


def test_get_vault_secret_succeeds(context, base_state):
    """Action reads the secret and returns its value when all conditions are met."""
    mock_client = unittest.mock.Mock()
    mock_client.read_secret.return_value = "my-secret-value"
    with unittest.mock.patch(VAULT_CLIENT, return_value=mock_client):
        context.run(
            context.on.action("get-vault-secret", params={"path": "p", "key": "k"}),
            base_state,
        )
    assert context.action_results == {"result": "my-secret-value"}
    mock_client.read_secret.assert_called_once_with(path="p", key="k")
