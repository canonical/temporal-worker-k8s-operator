# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration test config."""

import logging

import pytest
import pytest_asyncio
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    METADATA,
    WORKER_CONFIG,
    attach_worker_resource_file,
    get_application_url,
    setup_temporal_ecosystem,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

rsc_path = "./resource_sample/dist/python_samples-1.1.0-py3-none-any.whl"
env_rsc_path = "./resource_sample/sample.env"


@pytest.mark.skip_if_deployed
@pytest_asyncio.fixture(name="deploy", scope="module")
async def deploy(ops_test: OpsTest):
    """Verify the app is up and running."""
    await setup_temporal_ecosystem(ops_test)

    charm = await ops_test.build_charm(".")
    resources = {
        "temporal-worker-image": METADATA["containers"]["temporal-worker"]["upstream-source"],
        "workflows-file": rsc_path,
        "env-file": env_rsc_path,
    }

    await ops_test.model.deploy(charm, resources=resources, config=WORKER_CONFIG, application_name=APP_NAME)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="blocked",
            raise_on_blocked=False,
            timeout=600,
        )

        url = await get_application_url(ops_test, application=APP_NAME_SERVER, port=7233)
        await ops_test.model.applications[APP_NAME].set_config({"host": url})

        await attach_worker_resource_file(ops_test, rsc_type="workflows")
