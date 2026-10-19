#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration test helpers."""

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Generator
from datetime import timedelta
from pathlib import Path
from textwrap import dedent

import jubilant
import yaml
from temporallib.client import Client, Options

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
APP_NAME_SERVER = "temporal-k8s"
APP_NAME_ADMIN = "temporal-admin-k8s"

# Charm dependencies deployed alongside the worker. Channels are overridable via
# environment variables for the Juju 4.x nightly tests, which require
# postgresql-k8s 16/stable (14/stable does not support juju 4.x) and the 26.04
# revisions of the temporal charms.
POSTGRESQL_CHANNEL = os.getenv("POSTGRESQL_CHANNEL") or "14/stable"
# Revision pinned for 14/stable; set to an empty value to deploy the channel's
# latest revision (required when overriding to 16/stable).
POSTGRESQL_REVISION = os.getenv("POSTGRESQL_REVISION", "381")
# When set, deploy postgresql-k8s with force=True to bypass base checks.
# Required when postgresql-k8s has not yet declared explicit support for juju 4.x.
POSTGRESQL_FORCE = (os.getenv("POSTGRESQL_FORCE") or "").lower() in ("1", "true", "yes")
TEMPORAL_CHANNEL = os.getenv("TEMPORAL_CHANNEL") or "1.23/stable"
TEMPORAL_BASE = os.getenv("TEMPORAL_BASE") or "ubuntu@24.04"

BASE_WORKER_CONFIG = {
    "namespace": "default",
    "queue": "test-queue",
}

ENVIRONMENT_WITH_VAULT_CONFIG = dedent(
    """
        env:
            - name: key1
              value: value1
            - name: key2
              value: value2
        vault:
            - path: vault-secrets
              name: vault-key1
              key: vault-secret1
            - path: vault-secrets
              name: vault-key2
              key: vault-secret2
        """
)


@contextlib.contextmanager
def fast_forward(juju: jubilant.Juju, interval: str = "10s") -> Generator[None, None, None]:
    """Temporarily speed up update-status hooks.

    Args:
        juju: Jubilant Juju client bound to the test model.
        interval: update-status-hook-interval value while in the context.
    """
    config = juju.model_config() or {}
    old = config.get("update-status-hook-interval", "5m")
    juju.model_config({"update-status-hook-interval": interval})
    try:
        yield
    finally:
        juju.model_config({"update-status-hook-interval": old})


def get_worker_config(secret_id):
    """Get worker charm config.

    Args:
        secret_id: Juju secret id.

    Returns:
        Temporal worker charm config
    """
    return {
        **BASE_WORKER_CONFIG,
        "environment": dedent(
            f"""
        env:
            - name: message
              value: hello
            - name: key2
              value: value2
        juju:
            - secret-id: {secret_id}
              name: juju-key1
              key: juju-secret1
            - secret-id: {secret_id}
              name: juju-key2
              key: juju-secret2
        """
        ),
    }


def add_juju_secret(juju: jubilant.Juju) -> str:
    """Add Juju user secret to model.

    Args:
        juju: Jubilant Juju client bound to the test model.

    Returns:
        secret ID of created secret.
    """
    secret_uri = juju.add_secret("worker-secrets", {"juju-secret1": "world", "juju-secret2": "value2"})
    return secret_uri.unique_identifier


def add_vault_secret(juju: jubilant.Juju, path: str, key: str, value: str):
    """Add Vault secret using charm action.

    Args:
        juju: Jubilant Juju client bound to the test model.
        path: Path to write to.
        key: Key to write secret to.
        value: Secret value to write.
    """
    secret_added = False
    for _ in range(10):
        try:
            task = juju.run(
                f"{APP_NAME}/0",
                "add-vault-secret",
                {"path": path, "key": key, "value": value},
            )
        except jubilant.TaskError as e:
            logger.info("add vault secret attempt failed: %s", e)
            time.sleep(2)
            continue
        result = task.results
        logger.info("add vault secret result: %s", result)
        if "result" in result and result["result"] == "secret successfully created":
            secret_added = True
            break
        time.sleep(2)

    assert secret_added


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


def run_sample_workflow(juju: jubilant.Juju, workflow_type=None, use_env_variables=False):
    """Connect a client and run a basic Temporal workflow.

    Args:
        juju: Jubilant Juju client bound to the test model.
        workflow_type: set to "vault" to test Vault workflow.
        use_env_variables: whether to initialize Temporal client using environment variables or declared parameters.
    """
    url = get_application_url(juju, application=APP_NAME_SERVER, port=7233)
    logger.info("running workflow on app address: %s", url)
    result = asyncio.run(_run_sample_workflow(url, workflow_type, use_env_variables))
    logger.info("result: %s", result)
    assert result == "hello world"


async def _run_sample_workflow(url: str, workflow_type, use_env_variables):
    """Run the sample workflow against the given frontend address.

    Args:
        url: Temporal frontend host:port.
        workflow_type: workflow variant to run.
        use_env_variables: initialize the client from environment variables.

    Returns:
        The workflow result.
    """
    if use_env_variables:
        os.environ["TEMPORAL_HOST"] = url
        os.environ["TEMPORAL_NAMESPACE"] = BASE_WORKER_CONFIG["namespace"]
        os.environ["TEMPORAL_QUEUE"] = BASE_WORKER_CONFIG["queue"]
        client = await Client.connect(Options())
    else:
        client = await Client.connect(
            Options(host=url, queue=BASE_WORKER_CONFIG["queue"], namespace=BASE_WORKER_CONFIG["namespace"])
        )

    workflow_name = "GreetingWorkflow"
    if workflow_type == "vault":
        workflow_name = "VaultWorkflow"
    if workflow_type == "database":
        workflow_name = "DatabaseWorkflow"

    # Execute workflow
    return await client.execute_workflow(
        workflow_name,
        "placeholder",
        id="my-workflow-id",
        task_queue=BASE_WORKER_CONFIG["queue"],
        run_timeout=timedelta(seconds=20),
    )


def register_temporal_namespace(juju: jubilant.Juju, namespace: str):
    """Register a namespace on the Temporal server via the admin charm CLI action.

    Args:
        juju: Jubilant Juju client bound to the test model.
        namespace: Temporal namespace name to register.
    """
    task = juju.run(
        f"{APP_NAME_ADMIN}/0",
        "cli",
        {"args": f"operator namespace create --namespace {namespace} --retention 3d"},
    )
    logger.info("cli namespace %s: %s", namespace, task.results)


def get_application_url(juju: jubilant.Juju, application, port):
    """Return application URL from the model.

    Args:
        juju: Jubilant Juju client bound to the test model.
        application: Name of application.
        port: Port number of the URL.

    Returns:
        Application URL of the form {address}:{port}
    """
    status = juju.status()
    address = status.apps[application].address
    return f"{address}:{port}"


def get_unit_url(juju: jubilant.Juju, application, unit, port, protocol="http"):
    """Return unit URL from the model.

    Args:
        juju: Jubilant Juju client bound to the test model.
        application: Name of application.
        unit: Number of the unit.
        port: Port number of the URL.
        protocol: Transfer protocol (default: http).

    Returns:
        Unit URL of the form {protocol}://{address}:{port}
    """
    status = juju.status()
    address = status.apps[application].units[f"{application}/{unit}"].address
    return f"{protocol}://{address}:{port}"


def perform_temporal_integrations(juju: jubilant.Juju):
    """Integrate Temporal charm with postgresql and admin charms.

    Args:
        juju: Jubilant Juju client bound to the test model.
    """
    juju.integrate(f"{APP_NAME_SERVER}:db", "postgresql-k8s:database")
    juju.integrate(f"{APP_NAME_SERVER}:visibility", "postgresql-k8s:database")
    juju.integrate(f"{APP_NAME_SERVER}:admin", f"{APP_NAME_ADMIN}:admin")
    juju.integrate(f"{APP_NAME_SERVER}:temporal-host-info", f"{APP_NAME_ADMIN}:temporal-host-info")
    juju.wait(lambda status: jubilant.all_active(status, APP_NAME_SERVER), timeout=180)

    assert juju.status().apps[APP_NAME_SERVER].units[f"{APP_NAME_SERVER}/0"].workload_status.is_active()


def scale(juju: jubilant.Juju, app, units):
    """Scale the application to the provided number and wait for idle.

    Args:
        juju: Jubilant Juju client bound to the test model.
        app: Application to be scaled.
        units: Number of units required.
    """
    juju.cli("scale-application", app, str(units))

    with fast_forward(juju):
        juju.wait(
            lambda status: jubilant.all_active(status, app) and len(status.apps[app].units) == units,
            timeout=600,
            successes=30,
        )

    assert len(juju.status().apps[app].units) == units


def setup_temporal_ecosystem(juju: jubilant.Juju):
    """Deploy the Temporal server, admin and postgresql apps and relate them.

    Args:
        juju: Jubilant Juju client bound to the test model.
    """
    juju.deploy(APP_NAME_SERVER, channel=TEMPORAL_CHANNEL, config={"num-history-shards": 1}, base=TEMPORAL_BASE)
    juju.deploy(APP_NAME_ADMIN, channel=TEMPORAL_CHANNEL, base=TEMPORAL_BASE)
    juju.deploy(
        "postgresql-k8s",
        channel=POSTGRESQL_CHANNEL,
        trust=True,
        revision=int(POSTGRESQL_REVISION) if POSTGRESQL_REVISION else None,
        force=POSTGRESQL_FORCE,
    )

    with fast_forward(juju):
        juju.wait(lambda status: jubilant.all_blocked(status, APP_NAME_SERVER, APP_NAME_ADMIN), timeout=600)
        juju.wait(lambda status: jubilant.all_active(status, "postgresql-k8s"), timeout=600)

        perform_temporal_integrations(juju)

        register_temporal_namespace(juju, "default")

        juju.wait(lambda status: jubilant.all_active(status, APP_NAME_SERVER), timeout=300)
        assert juju.status().apps[APP_NAME_SERVER].units[f"{APP_NAME_SERVER}/0"].workload_status.is_active()


def read_unit_statuses(juju: jubilant.Juju, application: str):
    """Read the status of an application's units.

    Args:
        juju: Jubilant Juju client bound to the test model.
        application: name of application to read status of

    Returns:
        The status of application units: name, status (active, blocked etc.),
        agent (idle, executing), address and message.
    """
    status = juju.status()
    app = status.apps.get(application)
    output = []
    for unit_name, unit in app.units.items() if app else []:
        output.append(
            {
                "unit": unit_name,
                "status": unit.workload_status.current,
                "agent": unit.juju_status.current,
                "address": unit.address,
                "message": unit.workload_status.message,
            }
        )
    return output


def wait_for_status_message(
    juju: jubilant.Juju, application: str, count: int, expected_message: str, timeout: int = 100, cadence: int = 2
):
    """Wait for the correct application status messages to appear.

    Args:
        juju: Jubilant Juju client bound to the test model.
        application: Name of application to wait for status of
        count: How many units that are expected to be emitting the expected message
        expected_message: The message that application units should be setting as a status message
        timeout: Wait time in seconds
        cadence: How long to wait before running the command again

    Raises:
        TimeoutError: If the expected amount of statuses weren't found in the given timeout.
    """
    while timeout > 0:
        application_status = read_unit_statuses(juju, application)
        seen = 0
        for row in application_status:
            if row.get("message") == expected_message:
                seen += 1

        if seen == count:
            return
        time.sleep(cadence)
        timeout -= cadence
    raise TimeoutError(f"Application {application} didn't show the expected status")


def authorize_charm(juju: jubilant.Juju, root_token: str):
    """Authorize the Vault charm by executing the 'authorize-charm' action on the leader unit.

    Args:
        juju: Jubilant Juju client bound to the test model.
        root_token (str): The root token used for authorization.

    Returns:
        The result of the action, which could be of any type or a dictionary.
    """
    leader_unit = get_leader_unit(juju, "vault-k8s")
    secret_uri = juju.add_secret("approle-token-vault-k8s", {"token": root_token})
    juju.grant_secret("approle-token-vault-k8s", "vault-k8s")
    task = juju.run(leader_unit, "authorize-charm", {"secret-id": secret_uri.unique_identifier}, wait=120)
    return task.results


def get_leader_unit(juju: jubilant.Juju, application_name: str) -> str:
    """Return the leader unit name for the given application.

    Args:
        juju: Jubilant Juju client bound to the test model.
        application_name: Name of application.

    Returns:
        The leader unit name.

    Raises:
        RuntimeError: If leader unit is not found.
    """
    for unit_name, unit in juju.status().apps[application_name].units.items():
        if unit.leader:
            return unit_name
    raise RuntimeError(f"Leader unit for `{application_name}` not found.")
