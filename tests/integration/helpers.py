#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal charm integration test helpers."""

import logging
from pathlib import Path

import yaml
from pytest_operator.plugin import OpsTest
from temporal_client.activities import ComposeGreetingInput
from temporal_client.workflows import GreetingWorkflow
from temporalio.client import Client

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
APP_NAME_SERVER = "temporal-k8s"
APP_NAME_ADMIN = "temporal-admin-k8s"
APP_NAME_UI = "temporal-ui-k8s"

WORKER_CONFIG = {
    "log-level": "debug",
    "namespace": "default",
    "queue": "my-task-queue",
    "auth-enabled": False,
    "auth-provider": "candid",
    "candid-url": "test-url",
    "candid-username": "test-username",
    "candid-private-key": "test-private-key",
    "candid-public-key": "test-public-key",
}


async def run_sample_workflow(ops_test: OpsTest):
    """Connect to a client and runs a basic Temporal workflow.

    Args:
        ops_test: PyTest object.
    """
    url = await get_application_url(ops_test, application=APP_NAME, port=7233)
    logger.info("running workflow on app address: %s", url)

    client = await Client.connect(url)

    # Execute workflow
    name = "Jean-luc"
    result = await client.execute_workflow(
        GreetingWorkflow.run, ComposeGreetingInput("Hello", name), id="my-workflow-id", task_queue="my-task-queue"
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


async def get_unit_url(ops_test: OpsTest, application, unit, port, protocol="http"):
    """Return unit URL from the model.

    Args:
        ops_test: PyTest object.
        application: Name of the application.
        unit: Number of the unit.
        port: Port number of the URL.
        protocol: Transfer protocol (default: http).

    Returns:
        Unit URL of the form {protocol}://{address}:{port}
    """
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][application]["units"][f"{application}/{unit}"]["address"]
    return f"{protocol}://{address}:{port}"


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
