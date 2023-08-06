# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

"""Temporal worker charm unit tests."""

import json
from unittest import TestCase, mock

from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness

from charm import TemporalWorkerK8SOperatorCharm
from state import State

CONTAINER_NAME = "temporal-worker"


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
        """The charm is blocked without a admin:temporal relation with a ready schema."""
        harness = self.harness

        config = {
            "log-level": "debug",
            "host": "test-host",
            "namespace": "test-namespace",
            "queue": "test-queue",
            "sentry-dsn": "",
            "workflows-file-name": "python_samples-1.1.0-py3-none-any.whl",
            "encryption-key": "",
            "auth-enabled": True,
            "auth-provider": "candid",
            "tls-root-cas": "",
            "candid-url": "test-url",
            "candid-username": "test-username",
            "candid-public-key": "test-public-key",
            "candid-private-key": "test-private-key",
            "oidc-auth-type": "",
            "oidc-project-id": "",
            "oidc-private-key-id": "",
            "oidc-private-key": "",
            "oidc-client-email": "",
            "oidc-client-id": "",
            "oidc-auth-uri": "",
            "oidc-token-uri": "",
            "oidc-auth-cert-url": "",
            "oidc-client-cert-url": "",
        }
        state = simulate_lifecycle(harness, config)
        harness.charm.on.config_changed.emit()

        sw = json.loads(state["supported_workflows"])
        sa = json.loads(state["supported_activities"])
        module_name = json.loads(state["module_name"])

        command = f"python worker.py '{json.dumps(dict(config))}' '{','.join(sw)}' '{','.join(sa)}' {module_name}"

        # The plan is generated after pebble is ready.
        want_plan = {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": command,
                    "startup": "disabled",
                    "override": "replace",
                }
            },
        }
        got_plan = harness.get_container_pebble_plan("temporal-worker").to_dict()
        self.assertEqual(got_plan, want_plan)

        # The service was started.
        service = harness.model.unit.get_container(CONTAINER_NAME).get_service("temporal-worker")
        self.assertTrue(service.is_running())

        # The ActiveStatus is set.
        self.assertEqual(
            harness.model.unit.status,
            ActiveStatus(f"worker listening to namespace {config['namespace']!r} on queue {config['queue']!r}"),
        )


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
        },
    )

    return harness.get_relation_data(rel, "temporal-worker-k8s")


class TestState(TestCase):
    """Unit tests for state.

    Attrs:
        maxDiff: Specifies max difference shown by failed tests.
    """

    maxDiff = None

    def test_get(self):
        """It is possible to retrieve attributes from the state."""
        state = make_state({"foo": json.dumps("bar")})
        self.assertEqual(state.foo, "bar")
        self.assertIsNone(state.bad)

    def test_set(self):
        """It is possible to set attributes in the state."""
        data = {"foo": json.dumps("bar")}
        state = make_state(data)
        state.foo = 42
        state.list = [1, 2, 3]
        self.assertEqual(state.foo, 42)
        self.assertEqual(state.list, [1, 2, 3])
        self.assertEqual(data, {"foo": "42", "list": "[1, 2, 3]"})

    def test_del(self):
        """It is possible to unset attributes in the state."""
        data = {"foo": json.dumps("bar"), "answer": json.dumps(42)}
        state = make_state(data)
        del state.foo
        self.assertIsNone(state.foo)
        self.assertEqual(data, {"answer": "42"})
        # Deleting a name that is not set does not error.
        del state.foo

    def test_is_ready(self):
        """The state is not ready when it is not possible to get relations."""
        state = make_state({})
        self.assertTrue(state.is_ready())

        state = State("myapp", lambda: None)
        self.assertFalse(state.is_ready())


def make_state(data):
    """Create state object.

    Args:
        data: Data to be included in state.

    Returns:
        State object with data.
    """
    app = "myapp"
    rel = type("Rel", (), {"data": {app: data}})()
    return State(app, lambda: rel)
