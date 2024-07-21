# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration test config."""

import logging
from pathlib import Path

import pytest
import pytest_asyncio
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    add_juju_secret,
    get_worker_config,
    setup_temporal_ecosystem,
)
from pytest import FixtureRequest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

env_rsc_path = "./resource_sample/sample.env"


@pytest.fixture(scope="module", name="temporal_worker_image")
def temporal_worker_image_fixture(request: FixtureRequest) -> str:
    """Fetch the OCI image for Temporal Worker charm."""
    temporal_worker_image = request.config.getoption("--temporal-worker-image")
    assert (
        temporal_worker_image
    ), "--temporal-worker-image argument is required which should contain the name of the OCI image."
    return temporal_worker_image


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
async def deploy(ops_test: OpsTest, charm: str, temporal_worker_image: str):
    """Verify the app is up and running."""
    await ops_test.model.set_config({"update-status-hook-interval": "1m"})

    resources = {
        "temporal-worker-image": temporal_worker_image,
    }

    secret_id = await add_juju_secret(ops_test)
    worker_config = get_worker_config(secret_id)

    await ops_test.model.deploy(charm, resources=resources, config=worker_config, application_name=APP_NAME)
    await ops_test.model.grant_secret("worker-secrets", APP_NAME)

    await setup_temporal_ecosystem(ops_test)
    await ops_test.model.applications[APP_NAME].set_config({"host": f"{APP_NAME_SERVER}:7233"})

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            raise_on_blocked=False,
            timeout=600,
        )

        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
