# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the vault action handlers: add-vault-secret and get-vault-secret.

Two testing strategies are used:

Direct unit tests call the action methods with a plain Mock event so that
event.fail() is a no-op rather than an exception. This lets each test verify
that a guard clause stops execution (no set_results call, no downstream
vault operations) rather than relying on an exception to short-circuit the
handler.

Scenario tests use ops.testing.Context with the full ops framework. They
exercise the happy path and verify that the correct container name is used
to check workload connectivity.
"""

import unittest.mock

import ops.testing
import pytest

from vault.actions import VaultActions

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_vault_actions(mock_charm):
    """Return a VaultActions bound to mock_charm, bypassing the ops framework."""
    obj = object.__new__(VaultActions)
    obj.charm = mock_charm
    return obj


def _connected_mock_charm():
    """Return a mock charm with a connected workload container and a vault relation."""
    mock_charm = unittest.mock.MagicMock()
    mock_charm._service_name = "temporal-worker"
    mock_charm.unit.get_container.return_value.can_connect.return_value = True
    return mock_charm


@pytest.fixture
def base_state(temporal_worker_container, vault_relation, peer_relation, config, vault_nonce_secret):
    """Minimal state with a connected container, vault relation, and peer relation."""
    return ops.testing.State(
        containers=[temporal_worker_container],
        relations=[vault_relation, peer_relation],
        config=config,
        secrets=[vault_nonce_secret],
    )


# ── add-vault-secret ──────────────────────────────────────────────────────────


def test_add_vault_secret_fails_if_validation_fails():
    """Action fails and does not proceed when the workload container is unreachable."""
    mock_event = unittest.mock.MagicMock()
    mock_charm = unittest.mock.MagicMock()
    mock_charm._service_name = "temporal-worker"
    mock_charm.unit.get_container.return_value.can_connect.return_value = False

    _make_vault_actions(mock_charm)._on_add_vault_secret(mock_event)

    mock_event.fail.assert_called_once_with("Failed to connect to the container")
    mock_charm.vault_relation.get_vault_client.assert_not_called()
    mock_event.set_results.assert_not_called()


def test_add_vault_secret_fails_if_params_missing():
    """Action fails and does not reach the vault client when required params are absent."""
    mock_event = unittest.mock.MagicMock()
    mock_event.params = {"path": "p"}  # key and value missing

    _make_vault_actions(_connected_mock_charm())._on_add_vault_secret(mock_event)

    mock_event.fail.assert_called_once_with("`path`, `key` and `value` are required parameters")
    mock_event.set_results.assert_not_called()


def test_add_vault_secret_fails_if_vault_client_unavailable():
    """Action fails and does not attempt a write when the vault client cannot be created."""
    mock_event = unittest.mock.MagicMock()
    mock_event.params = {"path": "p", "key": "k", "value": "v"}
    mock_charm = _connected_mock_charm()
    mock_charm.vault_relation.get_vault_client.side_effect = Exception("vault unreachable")

    _make_vault_actions(mock_charm)._on_add_vault_secret(mock_event)

    mock_event.fail.assert_called_once_with("Unable to initialize vault client. remove relation and retry.")
    mock_event.set_results.assert_not_called()


def test_add_vault_secret_succeeds(context, base_state):
    """Action writes the secret and returns a success result when all conditions are met."""
    mock_client = unittest.mock.Mock()
    with unittest.mock.patch("relations.vault.VaultRelation.get_vault_client", return_value=mock_client):
        context.run(
            context.on.action("add-vault-secret", params={"path": "p", "key": "k", "value": "v"}),
            base_state,
        )
    assert context.action_results == {"result": "secret successfully created"}
    mock_client.write_secret.assert_called_once_with(path="p", key="k", value="v")


# ── get-vault-secret ──────────────────────────────────────────────────────────


def test_get_vault_secret_fails_if_validation_fails():
    """Action fails and does not proceed when the workload container is unreachable."""
    mock_event = unittest.mock.MagicMock()
    mock_charm = unittest.mock.MagicMock()
    mock_charm._service_name = "temporal-worker"
    mock_charm.unit.get_container.return_value.can_connect.return_value = False

    _make_vault_actions(mock_charm)._on_get_vault_secret(mock_event)

    mock_event.fail.assert_called_once_with("Failed to connect to the container")
    mock_charm.vault_relation.get_vault_client.assert_not_called()
    mock_event.set_results.assert_not_called()


def test_get_vault_secret_fails_if_params_missing():
    """Action fails and does not reach the vault client when required params are absent."""
    mock_event = unittest.mock.MagicMock()
    mock_event.params = {"path": "p"}  # key missing

    _make_vault_actions(_connected_mock_charm())._on_get_vault_secret(mock_event)

    mock_event.fail.assert_called_once_with("`path` and `key` are required parameters")
    mock_event.set_results.assert_not_called()


def test_get_vault_secret_succeeds(context, base_state):
    """Action reads the secret and returns its value when all conditions are met."""
    mock_client = unittest.mock.Mock()
    mock_client.read_secret.return_value = "my-secret-value"
    with unittest.mock.patch("relations.vault.VaultRelation.get_vault_client", return_value=mock_client):
        context.run(
            context.on.action("get-vault-secret", params={"path": "p", "key": "k"}),
            base_state,
        )
    assert context.action_results == {"result": "my-secret-value"}
    mock_client.read_secret.assert_called_once_with(path="p", key="k")
