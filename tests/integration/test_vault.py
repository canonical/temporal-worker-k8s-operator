#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm vault relation integration tests."""

import logging

import hvac
import jubilant
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

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    def test_vault_relation(self, juju: jubilant.Juju):
        """Test Vault relation."""
        scale(juju, app=APP_NAME, units=2)

        # vault-k8s rev 502 crashes update-status if it fires while the
        # workload container is still coming up (pebble socket missing).
        juju.model_config({"update-status-hook-interval": "5m"})
        try:
            juju.deploy("vault-k8s", channel="1.16/stable")

            juju.wait(
                lambda status: jubilant.all_blocked(status, "vault-k8s"),
                timeout=1200,
            )

            # Container is up and charm is blocked
            juju.model_config({"update-status-hook-interval": "1m"})

            # Initialize vault
            logger.info("initializing vault-k8s charm")
            vault_url = get_unit_url(juju, "vault-k8s", 0, 8200, "https")
            client = hvac.Client(url=vault_url, verify=False)
            initialize_response = client.sys.initialize(secret_shares=1, secret_threshold=1)
            root_token, unseal_key = initialize_response["root_token"], initialize_response["keys"][0]
            unseal_vault(client, vault_url, root_token, unseal_key)

            logger.info("waiting for vault-k8s charm to go into blocked state")
            wait_for_status_message(
                juju,
                application="vault-k8s",
                count=1,
                expected_message="Please authorize charm (see `authorize-charm` action)",
            )

            logger.info("authorizing vault-k8s charm")
            authorize_charm(juju, root_token)
            juju.wait(
                lambda status: jubilant.all_active(status, "vault-k8s"),
                timeout=600,
            )

            logger.info("relating temporal-worker-k8s to vault-k8s charms")
            juju.integrate(APP_NAME, "vault-k8s")

            juju.wait(
                lambda status: jubilant.all_active(status, APP_NAME, "vault-k8s"),
                timeout=600,
            )

            logger.info("adding sample secrets to vault")
            add_vault_secret(juju, path="vault-secrets", key="vault-secret1", value="hello")
            add_vault_secret(juju, path="vault-secrets", key="vault-secret2", value="world")
            juju.config(APP_NAME, {"environment": ENVIRONMENT_WITH_VAULT_CONFIG})

            juju.wait(
                lambda status: jubilant.all_active(status, APP_NAME, "vault-k8s"),
                timeout=100,
            )

            run_sample_workflow(juju, workflow_type="vault")
        finally:
            juju.model_config({"update-status-hook-interval": "1m"})
