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
    authorize_charm,
    get_unit_url,
    run_sample_workflow,
    scale,
    unseal_vault,
    wait_for_vault_status_message,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    async def test_vault_relation(self, ops_test: OpsTest):
        """Test Vault relation."""
        await scale(ops_test, app=APP_NAME, units=2)
        await ops_test.model.deploy("vault-k8s", channel="1.15/edge")

        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(
                apps=["vault-k8s"],
                status="blocked",
                raise_on_blocked=False,
                timeout=600,
            )

            # Initialize vault
            vault_url = await get_unit_url(ops_test, "vault-k8s", 0, 8200, "https")
            client = hvac.Client(url=vault_url, verify=False)
            initialize_response = client.sys.initialize(secret_shares=1, secret_threshold=1)
            root_token, unseal_key = initialize_response["root_token"], initialize_response["keys"][0]
            unseal_vault(client, vault_url, root_token, unseal_key)

            await wait_for_vault_status_message(
                ops_test=ops_test,
                count=1,
                expected_message="Please authorize charm (see `authorize-charm` action)",
            )

            await authorize_charm(ops_test, root_token)
            await ops_test.model.wait_for_idle(
                apps=["vault-k8s"],
                status="active",
                timeout=600,
            )

            await ops_test.model.integrate(APP_NAME, "vault-k8s")

            await ops_test.model.wait_for_idle(
                apps=[APP_NAME, "vault-k8s"],
                status="active",
                raise_on_blocked=False,
                timeout=600,
            )

            await run_sample_workflow(ops_test, workflow_type="vault")
