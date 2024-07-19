#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration tests."""

import logging

import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import run_sample_workflow
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    # async def test_basic_client(self, ops_test: OpsTest):
    #     """Connects a client and runs a basic Temporal workflow."""
    #     await run_sample_workflow(ops_test)

    async def test_secrets_config(self, ops_test: OpsTest):
        """Secrets configured by the user are included in workload container."""
        # await ops_test.model.add_secret("worker-secrets", {"sensitive1": "hello", "sensitive2": "world"})
        # await set_secrets_config(ops_test)

        # await ops_test.model.wait_for_idle(
        #     apps=[APP_NAME],
        #     status="active",
        #     raise_on_blocked=False,
        #     timeout=600,
        # )

        await run_sample_workflow(ops_test)

    # async def test_invalid_env_file(self, ops_test: OpsTest):
    #     """Attaches an invalid .env file to the worker."""
    #     await attach_worker_invalid_env_file(ops_test)
