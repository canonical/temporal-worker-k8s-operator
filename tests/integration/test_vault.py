#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm vault relation integration tests."""

import logging

import hvac
import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import (
    APP_NAME,
    ENVIRONMENT_WITH_VAULT_CONFIG,
    add_vault_secret,
    authorize_charm,
    get_unit_url,
    run_sample_workflow,
    scale,
    unseal_vault,
    wait_for_status_message,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)
VAULT_K8S = "vault-k8s"
VAULT_K8S_CHANNEL = "1.16/stable"

@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    async def test_vault_relation(self, ops_test: OpsTest):
        """Test Vault relation."""
        await scale(ops_test, app=APP_NAME, units=2)

        await ops_test.model.deploy(VAULT_K8S, channel=VAULT_K8S_CHANNEL)

        async with ops_test.fast_forward():
            # Initialize vault
            await ops_test.model.wait_for_idle(
                apps=["vault-k8s"],
                status="blocked",
                raise_on_blocked=False,
                timeout=1600,
            )
            logger.info("initializing vault-k8s charm")
            vault_url = await get_unit_url(ops_test, VAULT_K8S, 0, 8200, "https")
            client = hvac.Client(url=vault_url, verify=False)
            initialize_response = client.sys.initialize(secret_shares=1, secret_threshold=1)
            root_token, unseal_key = initialize_response["root_token"], initialize_response["keys"][0]
            unseal_vault(client, vault_url, root_token, unseal_key)

            logger.info("authorizing vault-k8s charm")
            await authorize_charm(ops_test, root_token)

            # Integrate vault-k8s with temporal-worker-k8s
            logger.info("relating temporal-worker-k8s to vault-k8s charms")
            await ops_test.model.integrate(APP_NAME, VAULT_K8S)

            await ops_test.model.wait_for_idle(
                apps=[APP_NAME, VAULT_K8S],
                status="active",
                raise_on_blocked=False,
                timeout=900,
            )

            logger.info("adding sample secrets to vault")
            await add_vault_secret(ops_test, path="vault-secrets", key="vault-secret1", value="hello")
            await add_vault_secret(ops_test, path="vault-secrets", key="vault-secret2", value="world")
            await ops_test.model.applications[APP_NAME].set_config({"environment": ENVIRONMENT_WITH_VAULT_CONFIG})

            await ops_test.model.wait_for_idle(
                apps=[APP_NAME, VAULT_K8S],
                status="active",
                raise_on_blocked=False,
                timeout=100,
            )

            await run_sample_workflow(ops_test, workflow_type="vault")
