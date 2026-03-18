# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm temporal-worker-consumer integration tests."""

import logging
from pathlib import Path

import pytest
import pytest_asyncio
from helpers import APP_NAME
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(scope="module")
async def worker_consumer_requirer(ops_test: OpsTest) -> str | Path:
    """Fetch the path to charm."""
    charm = await ops_test.build_charm("./tests/integration/worker_consumer_requirer")
    assert charm, "Charm not built"
    return charm


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestTemporalHostInfoRelation:
    """Integration tests for temporal-worker-consumer relation."""

    async def test_relation(self, ops_test: OpsTest, worker_consumer_requirer: str | Path):
        """Verify requirer receives namespace and queue over relation."""
        cfg = {
            "namespace": "test-namespace",
            "queue": "test-queue",
        }
        await ops_test.model.applications[APP_NAME].set_config(cfg)
        # Deploy worker consumer requirer charm
        await ops_test.model.deploy(
            worker_consumer_requirer,
            application_name="worker-consumer-requirer",
        )
        await ops_test.model.wait_for_idle(
            apps=["worker-consumer-requirer"], status="waiting", raise_on_blocked=False, timeout=300
        )
        await ops_test.model.integrate(
            "worker-consumer-requirer:temporal-worker-consumer", f"{APP_NAME}:temporal-worker-consumer"
        )
        await ops_test.model.wait_for_idle(
            apps=["worker-consumer-requirer"], status="active", raise_on_blocked=False, timeout=300
        )
        requirer_app = ops_test.model.applications["worker-consumer-requirer"]
        requirer_unit = requirer_app.units[0]
        expected_status = "Temporal namespace: test-namespace, queue: test-queue"
        assert requirer_unit.workload_status == "active"
        assert requirer_unit.workload_status_message == expected_status
