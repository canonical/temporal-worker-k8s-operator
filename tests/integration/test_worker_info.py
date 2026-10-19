# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm temporal-worker-info integration tests."""

import logging
import pathlib
import subprocess

import jubilant
import pytest
from helpers import (
    APP_NAME,
    fast_forward,
    register_temporal_namespace,
    wait_for_status_message,
)

logger = logging.getLogger(__name__)

# Matches worker charm ActiveStatus (see src/charm.py: config namespace/queue use !r).
_EXPECTED_WORKER_STATUS = "worker listening to namespace 'test-namespace' on queue 'test-queue'"


@pytest.fixture(scope="module")
def worker_info_requirer_charm() -> pathlib.Path:
    """Pack the worker-info requirer test charm and return its path."""
    charm_dir = pathlib.Path("./tests/integration/worker_info_requirer")
    subprocess.run(["charmcraft", "pack"], cwd=charm_dir, check=True)
    packed = sorted(charm_dir.glob("*.charm"))
    assert packed, "worker-info requirer charm not packed"
    return packed[0].resolve()


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestTemporalWorkerInfoRelation:
    """Integration tests for temporal-worker-info relation."""

    def test_relation(
        self,
        juju: jubilant.Juju,
        worker_info_requirer_charm: pathlib.Path,
        temporal_worker_image: str,
    ):
        """Verify requirer receives namespace and queue over relation."""
        register_temporal_namespace(juju, "test-namespace")
        cfg = {
            "namespace": "test-namespace",
            "queue": "test-queue",
        }
        juju.config(APP_NAME, cfg)
        with fast_forward(juju):
            juju.wait(
                lambda status: jubilant.all_active(status, APP_NAME),
                timeout=600,
            )
        wait_for_status_message(juju, APP_NAME, 1, _EXPECTED_WORKER_STATUS, timeout=600, cadence=3)
        juju.deploy(
            worker_info_requirer_charm,
            app="worker-info-requirer",
            resources={"workload": temporal_worker_image},
        )
        juju.wait(
            lambda status: jubilant.all_waiting(status, "worker-info-requirer"),
            timeout=300,
        )
        juju.integrate("worker-info-requirer:temporal-worker-info", f"{APP_NAME}:temporal-worker-info")
        juju.wait(
            lambda status: jubilant.all_active(status, "worker-info-requirer"),
            timeout=300,
        )
        requirer_unit = juju.status().apps["worker-info-requirer"].units["worker-info-requirer/0"]
        expected_status = "Temporal namespace: test-namespace, queue: test-queue"
        assert requirer_unit.workload_status.current == "active"
        assert requirer_unit.workload_status.message == expected_status
