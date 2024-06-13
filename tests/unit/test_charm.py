# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

"""Temporal worker charm unit tests."""

import json
from unittest import TestCase, mock

from ops import Container
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import CheckStatus
from ops.testing import Harness

from charm import TemporalWorkerK8SOperatorCharm
from tests.unit.literals import CONFIG, CONTAINER_NAME, EXPECTED_VAULT_ENV, WANT_ENV


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

    @mock.patch("charm.TemporalWorkerK8SOperatorCharm._process_wheel_file")
    def test_attach_resource(self, _process_wheel_file):
        """The workflows file resource can be attached."""
        harness = self.harness

        # Simulate peer relation readiness.
        harness.add_relation("peer", "temporal")
        harness.add_resource("workflows-file", "")

        harness.charm.on.config_changed.emit()
        _process_wheel_file.assert_called()

        self.assertEqual(harness.model.unit.status, BlockedStatus("Invalid config: host value missing"))

    @mock.patch("charm.TemporalWorkerK8SOperatorCharm._process_wheel_file")
    @mock.patch("charm._setup_container")
    def test_ready(self, _process_wheel_file, _setup_container):
        """The charm is ready."""
        harness = self.harness

        state = simulate_lifecycle(harness, CONFIG)
        harness.charm.on.config_changed.emit()

        module_name = json.loads(state["module_name"])
        unpacked_file_name = json.loads(state["unpacked_file_name"])

        command = f"python worker.py {unpacked_file_name} {module_name}"

        # The plan is generated after pebble is ready.
        want_plan = {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": command,
                    "startup": "enabled",
                    "override": "replace",
                    "environment": WANT_ENV,
                    "on-check-failure": {"up": "ignore"},
                }
            },
            "checks": {
                "up": {
                    "override": "replace",
                    "level": "alive",
                    "period": "10s",
                    "exec": {"command": "python check_status.py"},
                }
            },
        }
        got_plan = harness.get_container_pebble_plan("temporal-worker").to_dict()
        self.assertEqual(got_plan, want_plan)

        # The service was started.
        service = harness.model.unit.get_container(CONTAINER_NAME).get_service("temporal-worker")
        self.assertTrue(service.is_running())

        self.assertEqual(harness.model.unit.status, MaintenanceStatus("replanning application"))

    @mock.patch("charm.TemporalWorkerK8SOperatorCharm._process_wheel_file")
    @mock.patch("charm._setup_container")
    @mock.patch.object(Container, "exec")
    def test_update_status_up(self, _process_wheel_file, _setup_container, mock_exec):
        """The charm updates the unit status to active based on UP status."""
        harness = self.harness
        mock_exec.return_value = mock.MagicMock(wait_output=mock.MagicMock(return_value=("", None)))

        simulate_lifecycle(harness, CONFIG)
        self.harness.container_pebble_ready(CONTAINER_NAME)

        container = harness.model.unit.get_container(CONTAINER_NAME)
        container.get_check = mock.Mock(status="up")
        container.get_check.return_value.status = CheckStatus.UP
        harness.charm.on.update_status.emit()

        self.assertEqual(
            harness.model.unit.status,
            ActiveStatus(f"worker listening to namespace {CONFIG['namespace']!r} on queue {CONFIG['queue']!r}"),
        )

    @mock.patch("charm.TemporalWorkerK8SOperatorCharm._process_wheel_file")
    @mock.patch("charm._setup_container")
    @mock.patch.object(Container, "exec")
    def test_update_status_down(self, _process_wheel_file, _setup_container, mock_exec):
        """The charm updates the unit status to maintenance based on DOWN status."""
        harness = self.harness
        mock_exec.return_value = mock.MagicMock(wait_output=mock.MagicMock(return_value=1))

        simulate_lifecycle(harness, CONFIG)
        self.harness.container_pebble_ready(CONTAINER_NAME)

        container = harness.model.unit.get_container(CONTAINER_NAME)
        container.get_check = mock.Mock(status="up")
        container.get_check.return_value.status = CheckStatus.DOWN
        harness.charm.on.update_status.emit()

        self.assertEqual(harness.model.unit.status, MaintenanceStatus("Status check: DOWN"))

    @mock.patch("charm.TemporalWorkerK8SOperatorCharm._process_wheel_file")
    @mock.patch("charm._setup_container")
    def test_vault_relation(self, _process_wheel_file, _setup_container):
        """The charm is ready with vault relation."""
        harness = self.harness

        state = simulate_lifecycle(harness, CONFIG)
        harness.charm.on.config_changed.emit()

        module_name = json.loads(state["module_name"])
        unpacked_file_name = json.loads(state["unpacked_file_name"])
        command = f"python worker.py {unpacked_file_name} {module_name}"

        relation_id = add_vault_relation(self, harness)
        self.harness.update_config({})

        # The plan is generated after pebble is ready.
        want_plan = {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": command,
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {**WANT_ENV, **EXPECTED_VAULT_ENV},
                    "on-check-failure": {"up": "ignore"},
                }
            },
            "checks": {
                "up": {
                    "override": "replace",
                    "level": "alive",
                    "period": "10s",
                    "exec": {"command": "python check_status.py"},
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
                    "command": command,
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {**WANT_ENV},
                    "on-check-failure": {"up": "ignore"},
                }
            },
            "checks": {
                "up": {
                    "override": "replace",
                    "level": "alive",
                    "period": "10s",
                    "exec": {"command": "python check_status.py"},
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

    Returns:
        Peer relation data.
    """
    # Simulate peer relation readiness.
    rel = harness.add_relation("peer", "temporal")

    # Simulate pebble readiness.
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.temporal_worker_pebble_ready.emit(container)

    harness.update_config(config)
    harness.add_resource("workflows-file", "bytes_content")

    harness.update_relation_data(
        rel,
        app_or_unit="temporal-worker-k8s",
        key_values={
            "supported_workflows": json.dumps(["TestWorkflow"]),
            "supported_activities": json.dumps(["test_activity"]),
            "module_name": json.dumps("python_samples"),
            "unpacked_file_name": json.dumps("python_sample-0.1.0"),
        },
    )

    return harness.get_relation_data(rel, "temporal-worker-k8s")
