# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration test config."""

import logging

import pytest
import pytest_asyncio
from helpers import (
    APP_NAME,
    APP_NAME_ADMIN,
    APP_NAME_SERVER,
    APP_NAME_UI,
    METADATA,
    WORKER_CONFIG,
    create_default_namespace,
    get_application_url,
    perform_temporal_integrations,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest_asyncio.fixture(name="deploy", scope="module")
async def deploy(ops_test: OpsTest, pytestconfig: pytest.Config):
    """Verify the app is up and running."""
    charm = pytestconfig.getoption("--charm-file")
    resources = {"temporal-worker-image": METADATA["containers"]["temporal-worker"]["upstream-source"]}

    # Deploy temporal server, temporal admin and postgresql charms.
    await ops_test.model.deploy(f"./{charm}", resources=resources, config=WORKER_CONFIG, application_name=APP_NAME)
    await ops_test.model.deploy(APP_NAME_SERVER, channel="edge")
    await ops_test.model.deploy(APP_NAME_ADMIN, channel="edge")
    await ops_test.model.deploy(APP_NAME_UI, channel="edge")
    await ops_test.model.deploy("postgresql-k8s", channel="14", trust=True)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME, APP_NAME_SERVER, APP_NAME_ADMIN, APP_NAME_UI],
            status="blocked",
            raise_on_blocked=False,
            timeout=600,
        )
        await ops_test.model.wait_for_idle(
            apps=["postgresql-k8s"], status="active", raise_on_blocked=False, timeout=600
        )

        await perform_temporal_integrations(ops_test)

        await create_default_namespace(ops_test)

        await ops_test.model.wait_for_idle(apps=[APP_NAME_SERVER], status="active", raise_on_blocked=False, timeout=300)
        assert ops_test.model.applications[APP_NAME_SERVER].units[0].workload_status == "active"
        assert ops_test.model.applications[APP_NAME_UI].units[0].workload_status == "active"

        url = await get_application_url(ops_test, application=APP_NAME_SERVER, port=7233)

        await ops_test.model.applications[APP_NAME].set_config({"host": url})

        rsc_name = "workflows-file"
        # TODO(kelkawi-a): build wheel file here and refer to it
        rsc_path = "./resource_sample/dist/python_samples-1.1.0-py3-none-any.whl"
        logger.info(f"Attaching resource: attach-resource {APP_NAME} {rsc_name}={rsc_path}")
        await ops_test.juju("attach-resource", APP_NAME, f"{rsc_name}={rsc_path}")

        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", raise_on_blocked=False, timeout=120)
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
