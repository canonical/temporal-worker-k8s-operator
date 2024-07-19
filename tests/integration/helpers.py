#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal charm integration test helpers."""

import asyncio
import logging
import time
from datetime import timedelta
from pathlib import Path
from textwrap import dedent

import yaml
from pytest_operator.plugin import OpsTest
from temporallib.client import Client, Options

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
APP_NAME_SERVER = "temporal-k8s"
APP_NAME_ADMIN = "temporal-admin-k8s"

WORKER_CONFIG = {
    "host": f"{APP_NAME_SERVER}:7233",
    "namespace": "default",
    "queue": "test-queue",
    "secrets": dedent(
        """
    secrets:
        env:
            - key1: value1
            - key2: value2
        juju:
            - secret-name: worker-secrets
              key: sensitive1
            - secret-name: worker-secrets
              key: sensitive2
    """
    ),
}


def get_worker_config(secret_id):
    """Get worker charm config.

    Args:
        secret_id: Juju secret id.
    """
    return {
        "host": f"{APP_NAME_SERVER}:7233",
        "namespace": "default",
        "queue": "test-queue",
        "secrets": dedent(
            f"""
        secrets:
            env:
                - key1: value1
                - key2: value2
            juju:
                - secret-id: {secret_id}
                key: sensitive1
                - secret-id: {secret_id}
                key: sensitive2
        """
        ),
    }


def unseal_vault(client, endpoint: str, root_token: str, unseal_key: str):
    """Unseal a Vault instance if it is currently sealed.

    Args:
        client: Vault client
        endpoint: The URL endpoint of the Vault instance.
        root_token: The root token used to authenticate with the Vault.
        unseal_key: The unseal key used to unseal the Vault.
    """
    client.token = root_token
    if not client.sys.is_sealed():
        return
    client.sys.submit_unseal_key(unseal_key)


async def run_sample_workflow(ops_test: OpsTest, workflow_type=None):
    """Connect to a client and runs a basic Temporal workflow.

    Args:
        ops_test: PyTest object.
        workflow_type: set to "vault" to test Vault workflow.
    """
    url = await get_application_url(ops_test, application=APP_NAME_SERVER, port=7233)
    logger.info("running workflow on app address: %s", url)

    client = await Client.connect(Options(host=url, queue=WORKER_CONFIG["queue"], namespace=WORKER_CONFIG["namespace"]))

    workflow_name = "GreetingWorkflow"
    if workflow_type == "vault":
        workflow_name = "VaultWorkflow"

    # Execute workflow
    name = "Jean-luc"
    result = await client.execute_workflow(
        workflow_name, name, id="my-workflow-id", task_queue=WORKER_CONFIG["queue"], run_timeout=timedelta(seconds=20)
    )
    logger.info(f"result: {result}")
    assert result == "hello world"

    # assert result == f"Hello, {name}!"


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
    await ops_test.model.wait_for_idle(apps=[APP_NAME_SERVER], status="active", raise_on_blocked=False, timeout=180)

    assert ops_test.model.applications[APP_NAME_SERVER].units[0].workload_status == "active"


async def scale(ops_test: OpsTest, app, units):
    """Scale the application to the provided number and wait for idle.

    Args:
        ops_test: PyTest object.
        app: Application to be scaled.
        units: Number of units required.
    """
    await ops_test.model.applications[app].scale(scale=units)

    async with ops_test.fast_forward():
        # Wait for model to settle
        await ops_test.model.wait_for_idle(
            apps=[app],
            status="active",
            idle_period=30,
            raise_on_error=False,
            raise_on_blocked=True,
            timeout=600,
            wait_for_exact_units=units,
        )

    assert len(ops_test.model.applications[app].units) == units


async def setup_temporal_ecosystem(ops_test: OpsTest):
    """Scale the application to the provided number and wait for idle.

    Args:
        ops_test: PyTest object.
    """
    await asyncio.gather(
        ops_test.model.deploy(APP_NAME_SERVER, channel="edge", config={"num-history-shards": 1}),
        ops_test.model.deploy(APP_NAME_ADMIN, channel="edge"),
        ops_test.model.deploy("postgresql-k8s", channel="14/stable", trust=True),
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME_SERVER, APP_NAME_ADMIN],
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


async def attach_worker_invalid_env_file(ops_test: OpsTest):
    """Scale the application to the provided number and wait for idle.

    Args:
        ops_test: PyTest object.
    """
    rsc_name = "env-file"
    rsc_path = "./sample_files/invalid.env"

    logger.info(f"Attaching resource: {APP_NAME} {rsc_name}={rsc_path}")
    with open(rsc_path, "rb") as file:
        ops_test.model.applications[APP_NAME].attach_resource(rsc_name, rsc_path, file)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="blocked", raise_on_error=False, raise_on_blocked=False, timeout=600
    )
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "blocked"


async def read_vault_unit_statuses(ops_test: OpsTest):
    """Read the complete status from vault units.

    Reads the statuses that juju emits that aren't captured by ops_test together. Captures a vault
    units: name, status (active, blocked etc.), agent (idle, executing), address and message.

    Args:
        ops_test: Ops test Framework

    Returns:
        The status of vault units

    Raises:
        Exception: if `juju status` does not return the expected format
    """
    status_tuple = await ops_test.juju("status")
    if status_tuple[0] != 0:
        raise Exception
    output = []
    for row in status_tuple[1].split("\n"):
        if not row.startswith("vault-k8s/"):
            continue
        cells = row.split(maxsplit=4)
        if len(cells) < 5:
            cells.append("")
        output.append(
            {
                "unit": cells[0],
                "status": cells[1],
                "agent": cells[2],
                "address": cells[3],
                "message": cells[4],
            }
        )
    return output


async def wait_for_vault_status_message(
    ops_test: OpsTest, count: int, expected_message: str, timeout: int = 100, cadence: int = 2
):
    """Wait for the correct vault status messages to appear.

    This function is necessary because ops_test doesn't provide the facilities to discriminate
    depending on the status message of the units, just the statuses themselves.

    Args:
        ops_test: Ops test Framework.
        count: How many units that are expected to be emitting the expected message
        expected_message: The message that vault units should be setting as a status message
        timeout: Wait time in seconds to get proxied endpoints.
        cadence: How long to wait before running the command again

    Raises:
        TimeoutError: If the expected amount of statuses weren't found in the given timeout.
    """
    while timeout > 0:
        vault_status = await read_vault_unit_statuses(ops_test)
        seen = 0
        for row in vault_status:
            if row.get("message") == expected_message:
                seen += 1

        if seen == count:
            return
        time.sleep(cadence)
        timeout -= cadence
    raise TimeoutError("Vault didn't show the expected status")


async def authorize_charm(ops_test: OpsTest, root_token: str):
    """Authorize the Vault charm by executing the 'authorize-charm' action on the leader unit.

    Args:
        ops_test: Ops test Framework.
        root_token (str): The root token used for authorization.

    Returns:
        The result of the action, which could be of any type or a dictionary.
    """
    assert ops_test.model
    leader_unit = await get_leader_unit(ops_test.model, "vault-k8s")
    secret = await ops_test.model.add_secret("approle-token-vault-k8s", [f"token={root_token}"])
    secret_id = secret.split(":")[-1]
    await ops_test.model.grant_secret("approle-token-vault-k8s", "vault-k8s")
    authorize_action = await leader_unit.run_action(
        action_name="authorize-charm",
        **{
            "secret-id": secret_id,
        },
    )
    result = await ops_test.model.get_action_output(action_uuid=authorize_action.entity_id, wait=120)
    return result


async def get_leader_unit(model, application_name: str):
    """Return the leader unit for the given application.

    Args:
        model: ops_test model
        application_name: Name of application.

    Returns:
        The leader unit.

    Raises:
        RuntimeError: If leader unit is not found.
    """
    for unit in model.units.values():
        if unit.application == application_name and await unit.is_leader_from_status():
            return unit
    raise RuntimeError(f"Leader unit for `{application_name}` not found.")
