# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration test config."""

import logging

import pytest
import pytest_asyncio
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    WORKER_CONFIG,
    get_application_url,
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


@pytest.mark.skip_if_deployed
@pytest_asyncio.fixture(name="deploy", scope="module")
async def deploy(ops_test: OpsTest, temporal_worker_image: str):
    """Verify the app is up and running."""
    await ops_test.model.set_config({"update-status-hook-interval": "1m"})

    resources = {
        "temporal-worker-image": temporal_worker_image,
        "env-file": env_rsc_path,
    }

    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, resources=resources, config=WORKER_CONFIG, application_name=APP_NAME)
    await setup_temporal_ecosystem(ops_test)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="blocked",
            raise_on_blocked=False,
            timeout=600,
        )

        url = await get_application_url(ops_test, application=APP_NAME_SERVER, port=7233)
        await ops_test.model.applications[APP_NAME].set_config({"host": url})
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            raise_on_blocked=False,
            timeout=600,
        )

        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
