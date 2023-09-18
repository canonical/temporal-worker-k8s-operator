#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal charm integration test helpers."""

import asyncio
import logging
from pathlib import Path

import yaml
from pytest_operator.plugin import OpsTest
from temporallib.client import Client, Options

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
APP_NAME_SERVER = "temporal-k8s"
APP_NAME_ADMIN = "temporal-admin-k8s"
APP_NAME_UI = "temporal-ui-k8s"

WORKER_CONFIG = {
    "namespace": "default",
    "queue": "test-queue",
    "workflows-file-name": "python_samples-1.1.0-py3-none-any.whl",
    "supported-workflows": "all",
    "supported-activities": "all",
}


async def run_sample_workflow(ops_test: OpsTest):
    """Connect to a client and runs a basic Temporal workflow.

    Args:
        ops_test: PyTest object.
    """
    url = await get_application_url(ops_test, application=APP_NAME_SERVER, port=7233)
    logger.info("running workflow on app address: %s", url)

    client = await Client.connect(Options(host=url, queue=WORKER_CONFIG["queue"], namespace="default"))

    # Execute workflow
    name = "Jean-luc"
    result = await client.execute_workflow(
        "GreetingWorkflow",
        name,
        id="my-workflow-id",
        task_queue=WORKER_CONFIG["queue"],
    )
    logger.info(f"result: {result}")
    assert result == f"Hello, {name}!"


async def create_default_namespace(ops_test: OpsTest):
    """Create default namespace on Temporal server using tctl.

    Args:
        ops_test: PyTest object.
    """
    # Register default namespace from admin charm.
    action = (
        await ops_test.model.applications[APP_NAME_ADMIN]
        .units[0]
        .run_action("tctl", args="--ns default namespace register -rd 3")
    )
    result = (await action.wait()).results
    logger.info(f"tctl result: {result}")
    assert "result" in result and result["result"] == "command succeeded"


async def get_application_url(ops_test: OpsTest, application, port):
    """Return application URL from the model.

    Args:
        ops_test: PyTest object.
        application: Name of the application.
        port: Port number of the URL.

    Returns:
        Application URL of the form {address}:{port}
    """
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][application].public_address
    return f"{address}:{port}"


async def perform_temporal_integrations(ops_test: OpsTest):
    """Integrate Temporal charm with postgresql, admin and ui charms.

    Args:
        ops_test: PyTest object.
    """
    await ops_test.model.integrate(f"{APP_NAME_SERVER}:db", "postgresql-k8s:database")
    await ops_test.model.integrate(f"{APP_NAME_SERVER}:visibility", "postgresql-k8s:database")
    await ops_test.model.integrate(f"{APP_NAME_SERVER}:admin", f"{APP_NAME_ADMIN}:admin")
    await ops_test.model.wait_for_idle(apps=[APP_NAME_SERVER], status="active", raise_on_blocked=False, timeout=180)
    await ops_test.model.integrate(f"{APP_NAME_SERVER}:ui", f"{APP_NAME_UI}:ui")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME_SERVER, APP_NAME_UI], status="active", raise_on_blocked=False, timeout=180
    )

    assert ops_test.model.applications[APP_NAME_SERVER].units[0].workload_status == "active"


async def scale(ops_test: OpsTest, app, units):
    """Scale the application to the provided number and wait for idle.

    Args:
        ops_test: PyTest object.
        app: Application to be scaled.
        units: Number of units required.
    """
    await ops_test.model.applications[app].scale(scale=units)

    # Wait for model to settle
    await ops_test.model.wait_for_idle(
        apps=[app],
        status="active",
        idle_period=30,
        raise_on_error=False,
        raise_on_blocked=True,
        timeout=300,
        wait_for_exact_units=units,
    )

    assert len(ops_test.model.applications[app].units) == units


async def setup_temporal_ecosystem(ops_test: OpsTest):
    """Scale the application to the provided number and wait for idle.

    Args:
        ops_test: PyTest object.
    """
    await asyncio.gather(
        ops_test.model.deploy(APP_NAME_SERVER, channel="edge"),
        ops_test.model.deploy(APP_NAME_ADMIN, channel="edge"),
        ops_test.model.deploy(APP_NAME_UI, channel="edge"),
        ops_test.model.deploy("postgresql-k8s", channel="14", trust=True),
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME_SERVER, APP_NAME_ADMIN, APP_NAME_UI],
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


async def attach_worker_resource_file(ops_test: OpsTest, rsc_type="workflows"):
    """Scale the application to the provided number and wait for idle.

    Args:
        ops_test: PyTest object.
        rsc_type: Resource type.
    """
    if rsc_type == "workflows":
        rsc_name = "workflows-file"
        rsc_path = "./resource_sample/dist/python_samples-1.1.0-py3-none-any.whl"
    else:
        rsc_name = "env-file"
        rsc_path = "./resource_sample/invalid.env"

    logger.info(f"Attaching resource: {APP_NAME} {rsc_name}={rsc_path}")
    with open(rsc_path, "rb") as file:
        ops_test.model.applications[APP_NAME].attach_resource(rsc_name, rsc_path, file)

    if rsc_type == "workflows":
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_error=False, raise_on_blocked=False, timeout=600
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
    else:
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="blocked", raise_on_error=False, raise_on_blocked=False, timeout=600
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "blocked"
