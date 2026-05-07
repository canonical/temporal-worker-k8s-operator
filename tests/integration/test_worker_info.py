# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm temporal-worker-info integration tests."""

import logging
from pathlib import Path

import pytest
import pytest_asyncio
from helpers import APP_NAME, register_temporal_namespace, wait_for_status_message
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

# Matches worker charm ActiveStatus (see src/charm.py: config namespace/queue use !r).
_EXPECTED_WORKER_STATUS = "worker listening to namespace 'test-namespace' on queue 'test-queue'"


@pytest_asyncio.fixture(scope="module")
async def worker_info_requirer_charm(ops_test: OpsTest) -> str | Path:
    """Fetch the path to charm."""
    charm = await ops_test.build_charm("./tests/integration/worker_info_requirer")
    assert charm, "Charm not built"
    return charm


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestTemporalWorkerInfoRelation:
    """Integration tests for temporal-worker-info relation."""

    async def test_relation(
        self,
        ops_test: OpsTest,
        worker_info_requirer_charm: str | Path,
        temporal_worker_image: str,
    ):
        """Verify requirer receives namespace and queue over relation."""
        await register_temporal_namespace(ops_test, "test-namespace")
        cfg = {
            "namespace": "test-namespace",
            "queue": "test-queue",
        }
        await ops_test.model.applications[APP_NAME].set_config(cfg)
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME],
                status="active",
                raise_on_blocked=False,
                timeout=600,
            )
        await wait_for_status_message(ops_test, APP_NAME, 1, _EXPECTED_WORKER_STATUS, timeout=600, cadence=3)
        await ops_test.model.deploy(
            worker_info_requirer_charm,
            application_name="worker-info-requirer",
            resources={"workload": temporal_worker_image},
        )
        await ops_test.model.wait_for_idle(
            apps=["worker-info-requirer"], status="waiting", raise_on_blocked=False, timeout=300
        )
        await ops_test.model.integrate("worker-info-requirer:temporal-worker-info", f"{APP_NAME}:temporal-worker-info")
        await ops_test.model.wait_for_idle(
            apps=["worker-info-requirer"], status="active", raise_on_blocked=False, timeout=300
        )
        requirer_app = ops_test.model.applications["worker-info-requirer"]
        requirer_unit = requirer_app.units[0]
        expected_status = "Temporal namespace: test-namespace, queue: test-queue"
        assert requirer_unit.workload_status == "active"
        assert requirer_unit.workload_status_message == expected_status
