# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

"""Temporal worker charm unit tests."""

import json
from textwrap import dedent
from unittest import TestCase, mock

import yaml
from ops.jujuversion import JujuVersion
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Harness

from charm import TemporalWorkerK8SOperatorCharm
from tests.unit.literals import (
    CONFIG,
    CONTAINER_NAME,
    EXPECTED_VAULT_ENV,
    SECRETS_CONFIG,
    VAULT_CONFIG,
    WANT_ENV,
)


class TestCharm(TestCase):
    """Unit tests.

    Attrs:
        maxDiff: Specifies max difference shown by failed tests.
    """

    maxDiff = None

    def setUp(self):
        """Set up for the unit tests."""
        self.harness = Harness(TemporalWorkerK8SOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_can_connect(CONTAINER_NAME, True)
        self.harness.set_leader(True)
        self.harness.begin()

    def test_initial_plan(self):
        """The initial pebble plan is empty."""
        harness = self.harness
        initial_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
        self.assertEqual(initial_plan, {})

    def test_blocked_on_missing_host(self):
        """The charm is blocked on missing host config."""
        harness = self.harness

        # Simulate peer relation readiness.
        harness.add_relation("peer", "temporal")
        harness.charm.on.config_changed.emit()

        self.assertEqual(harness.model.unit.status, BlockedStatus("Invalid config: host value missing"))

    def test_ready(self):
        """The charm is ready."""
        harness = self.harness

        simulate_lifecycle(harness, CONFIG)
        harness.charm.on.config_changed.emit()

        # The plan is generated after pebble is ready.
        want_plan = {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": WANT_ENV,
                }
            },
        }
        got_plan = harness.get_container_pebble_plan("temporal-worker").to_dict()
        self.assertEqual(got_plan, want_plan)

        # The service was started.
        service = harness.model.unit.get_container(CONTAINER_NAME).get_service("temporal-worker")
        self.assertTrue(service.is_running())

        self.assertEqual(harness.model.unit.status, MaintenanceStatus("replanning application"))
        harness.charm.on.update_status.emit()

        self.assertEqual(
            harness.model.unit.status,
            ActiveStatus(f"worker listening to namespace {CONFIG['namespace']!r} on queue {CONFIG['queue']!r}"),
        )

    def test_vault_relation(self):
        """The charm is ready with vault relation."""
        harness = self.harness

        simulate_lifecycle(harness, CONFIG)
        harness.charm.on.config_changed.emit()

        relation_id = add_vault_relation(self, harness)
        self.harness.update_config({})

        # The plan is generated after pebble is ready.
        want_plan = {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {**WANT_ENV, **EXPECTED_VAULT_ENV},
                }
            },
        }

        got_plan = harness.get_container_pebble_plan("temporal-worker").to_dict()
        self.assertEqual(got_plan, want_plan)

        # Remove vault relation
        harness.remove_relation(relation_id)
        self.harness.update_config({})

        # The plan is generated after pebble is ready.
        want_plan = {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {**WANT_ENV},
                }
            },
        }

        got_plan = harness.get_container_pebble_plan("temporal-worker").to_dict()
        self.assertEqual(got_plan, want_plan)

    def test_invalid_secrets_config(self):
        """The charm raises goes into a blocked state if secrets config is incorrectly formatted."""
        harness = self.harness

        simulate_lifecycle(harness, CONFIG)
        harness.charm.on.config_changed.emit()
        invalid_secrets_config_env = dedent(
            """
        secrets:
            env:
              - hello: world
                wrong: key
        """
        )

        # with self.assertRaises(ValueError):
        harness.update_config({"secrets": invalid_secrets_config_env})
        self.assertEqual(
            harness.model.unit.status,
            BlockedStatus("Invalid secrets structure: 'env' should be a list of single-key dictionaries"),
        )

        invalid_secrets_config_juju = dedent(
            """
        secrets:
            juju:
              - wrong: key
                key: hello
        """
        )

        harness.update_config({"secrets": invalid_secrets_config_juju})
        self.assertEqual(
            harness.model.unit.status,
            BlockedStatus("Invalid secrets structure: 'juju' should be a list of dictionaries with 'secret-id' and 'key'"),
        )

        invalid_secrets_config_vault = dedent(
            """
        secrets:
            vault:
              - path: path
                value: wrong
        """
        )

        harness.update_config({"secrets": invalid_secrets_config_vault})
        self.assertEqual(
            harness.model.unit.status,
            BlockedStatus("Invalid secrets structure: 'vault' should be a list of dictionaries with 'path' and 'key'"),
        )

    @mock.patch("ops.jujuversion.JujuVersion.from_environ")
    @mock.patch("relations.vault.VaultRelation.get_vault_config", return_value=VAULT_CONFIG)
    @mock.patch("vault_client.VaultClient._authenticate", return_value=None)
    @mock.patch("vault_client.VaultClient.read_secret", return_value="token_secret")
    def test_valid_secrets_config(self, get_vault_config, _authenticate, read_secret, mock_from_environ):
        """The charm parses the secret config correctly."""
        harness = self.harness

        # Mock JujuVersion.from_environ().has_secrets
        mock_juju_version = mock.Mock()
        mock_juju_version.has_secrets = True
        mock_from_environ.return_value = mock_juju_version

        secret_id = simulate_lifecycle(harness, CONFIG)
        add_vault_relation(self, harness)
        self.harness.update_config({})

        secret_config = dedent(
            f"""
        secrets:
            env:
                - hello: world
                - test: variable
            juju:
                - secret-id: {secret_id}
                  key: sensitive1
                - secret-id: {secret_id}
                  key: sensitive2
            vault:
                - path: secrets
                  key: token
        """
        )
        harness.update_config({"secrets": secret_config})

        want_plan = {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {
                        **WANT_ENV,
                        **EXPECTED_VAULT_ENV,
                        # User added secrets through config
                        **{
                            "hello": "world",
                            "test": "variable",
                            "sensitive1": "hello",
                            "sensitive2": "world",
                            "token": "token_secret",
                        },
                    },
                }
            },
        }

        got_plan = harness.get_container_pebble_plan("temporal-worker").to_dict()
        self.assertEqual(got_plan, want_plan)


def add_vault_relation(test, harness):
    """Add vault relation to harness.

    Args:
        test: TestCharm object.
        harness: ops.testing.Harness object used to simulate charm lifecycle.

    Returns:
        Vault relation ID.
    """
    harness.charm.on.install.emit()
    relation_id = harness.add_relation("vault", "vault-k8s")
    harness.add_relation_unit(relation_id, "vault-k8s/0")

    data = harness.get_relation_data(relation_id, "temporal-worker-k8s/0")
    test.assertTrue(data)
    test.assertTrue("egress_subnet" in data)
    test.assertTrue("nonce" in data)

    secret_id = harness.add_model_secret(
        "vault-k8s/0",
        {"role-id": "111", "role-secret-id": "222"},
    )
    harness.grant_secret(secret_id, "temporal-worker-k8s")

    credentials = {data["nonce"]: secret_id}
    harness.update_relation_data(
        relation_id,
        "vault-k8s",
        {
            "vault_url": "127.0.0.1:8081",
            "ca_certificate": "abcd",
            "mount": "temporal-worker-k8s",
            "credentials": json.dumps(credentials, sort_keys=True),
        },
    )

    return relation_id


def simulate_lifecycle(harness, config):
    """Simulate a healthy charm life-cycle.

    Args:
        harness: ops.testing.Harness object used to simulate charm lifecycle.
        config: object to update the charm's config.
    """
    # Simulate peer relation readiness.
    harness.add_relation("peer", "temporal")

    # Simulate pebble readiness.
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.temporal_worker_pebble_ready.emit(container)

    harness.update_config(config)

    secret_id = harness.add_model_secret(
        "temporal-worker-k8s",
        {"sensitive1": "hello", "sensitive2": "world"},
    )

    return secret_id
