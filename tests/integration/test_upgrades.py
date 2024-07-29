#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm scaling integration tests."""

import logging
from pathlib import Path

import pytest
import pytest_asyncio
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    BASE_WORKER_CONFIG,
    add_juju_secret,
    get_worker_config,
    run_sample_workflow,
    setup_temporal_ecosystem,
)
from pytest import FixtureRequest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(scope="module", name="charm")
async def charm_fixture(request: FixtureRequest, ops_test: OpsTest) -> str | Path:
    """Fetch the path to charm."""
    charms = request.config.getoption("--charm-file")
    if not charms:
        charm = await ops_test.build_charm(".")
        assert charm, "Charm not built"
        return charm
    return charms[0]


@pytest.mark.skip_if_deployed
@pytest_asyncio.fixture(name="deploy", scope="module")
async def deploy(ops_test: OpsTest):
    """Verify the app is up and running."""
    await setup_temporal_ecosystem(ops_test)

    # Deploy Temporal worker charm from Charmhub store
    await ops_test.model.deploy(APP_NAME, config=BASE_WORKER_CONFIG, channel="edge")

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="blocked",
            raise_on_blocked=False,
            timeout=600,
        )

        await ops_test.model.applications[APP_NAME].set_config({"host": f"{APP_NAME_SERVER}:7233"})
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            raise_on_blocked=False,
            timeout=600,
        )


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestUpgrade:
    """Integration upgrade tests for Temporal worker charm."""

    async def test_upgrade(self, ops_test: OpsTest, charm: str):
        """Builds the current charm and refreshes the current deployment."""
        logger.info("Refreshing Temporal worker charm from local build")
        await ops_test.model.applications[APP_NAME].refresh(path=str(charm))
        secret_id = await add_juju_secret(ops_test)
        worker_config = get_worker_config(secret_id)

        await ops_test.model.applications[APP_NAME].set_config(worker_config)
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_error=False, raise_on_blocked=False, timeout=600
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

        await run_sample_workflow(ops_test)
