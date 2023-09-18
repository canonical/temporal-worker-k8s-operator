#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm scaling integration tests."""

import logging

import pytest
import pytest_asyncio
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    WORKER_CONFIG,
    attach_worker_resource_file,
    get_application_url,
    run_sample_workflow,
    setup_temporal_ecosystem,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest_asyncio.fixture(name="deploy", scope="module")
async def deploy(ops_test: OpsTest):
    """Verify the app is up and running."""
    await setup_temporal_ecosystem(ops_test)

    # Deploy Temporal worker charm from Charmhub store
    await ops_test.model.deploy(APP_NAME, config=WORKER_CONFIG)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="blocked",
            raise_on_blocked=False,
            timeout=600,
        )

        url = await get_application_url(ops_test, application=APP_NAME_SERVER, port=7233)
        await ops_test.model.applications[APP_NAME].set_config({"host": url})

        await attach_worker_resource_file(ops_test)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestUpgrade:
    """Integration upgrade tests for Temporal worker charm."""

    async def test_upgrade(self, ops_test: OpsTest):
        """Builds the current charm and refreshes the current deployment."""
        charm = await ops_test.build_charm(".")
        await ops_test.model.applications[APP_NAME].refresh(path=str(charm))
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_error=False, raise_on_blocked=False, timeout=600
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

        await run_sample_workflow(ops_test)
