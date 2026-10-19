#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm upgrade integration tests."""

import logging
import pathlib

import jubilant
import pytest
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    BASE_WORKER_CONFIG,
    add_juju_secret,
    fast_forward,
    get_worker_config,
    run_sample_workflow,
    setup_temporal_ecosystem,
)

logger = logging.getLogger(__name__)


@pytest.fixture(name="deploy", scope="module")
def deploy(juju: jubilant.Juju):
    """Verify the app is up and running."""
    setup_temporal_ecosystem(juju)

    # Deploy Temporal worker charm from Charmhub store
    juju.deploy(APP_NAME, config=BASE_WORKER_CONFIG, channel="edge")

    with fast_forward(juju):
        juju.wait(
            lambda status: jubilant.all_blocked(status, APP_NAME),
            timeout=600,
        )

        juju.config(APP_NAME, {"host": f"{APP_NAME_SERVER}:7233"})
        juju.wait(
            lambda status: jubilant.all_active(status, APP_NAME),
            timeout=600,
        )


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestUpgrade:
    """Integration upgrade tests for Temporal worker charm."""

    def test_upgrade(self, juju: jubilant.Juju, charm: pathlib.Path):
        """Refresh the current deployment to the locally built charm."""
        logger.info("Refreshing Temporal worker charm from local build")
        juju.refresh(
            APP_NAME,
            path=charm,
            base="ubuntu@24.04",
        )

        secret_id = add_juju_secret(juju)
        worker_config = get_worker_config(secret_id)

        juju.config(APP_NAME, worker_config)
        juju.wait(
            lambda status: jubilant.all_active(status, APP_NAME),
            timeout=600,
        )
        assert juju.status().apps[APP_NAME].units[f"{APP_NAME}/0"].workload_status.is_active()

        run_sample_workflow(juju)
