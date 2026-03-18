#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration tests."""

import logging

import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME, APP_NAME_SERVER, run_sample_workflow
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestHostInfo:
    """Integration tests for Temporal charm."""

    async def test_host_info_relation(self, ops_test: OpsTest):
        """Tests that workflows can be run using the host info relation data."""
        # host config option is set in deploy fixture and takes precedence over relation data
        # remove it and set relation
        await ops_test.model.set_config({"host": ""})
        await ops_test.model.integrate(f"{APP_NAME_SERVER}:temporal-host-info", f"{APP_NAME}:temporal-host-info")
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME],
                status="active",
                timeout=1000,
                raise_on_blocked=False,
            )
            await run_sample_workflow(ops_test, use_env_variables=False)

    async def test_host_info_relation_removed_blocks_until_restored(self, ops_test: OpsTest):
        """Ensure worker blocks when relation is removed and recovers after re-adding it."""
        await ops_test.juju(
            "remove-relation",
            f"{APP_NAME_SERVER}:temporal-host-info",
            f"{APP_NAME}:temporal-host-info",
        )
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME],
                status="blocked",
                timeout=1000,
                raise_on_blocked=False,
            )

        await ops_test.model.integrate(f"{APP_NAME_SERVER}:temporal-host-info", f"{APP_NAME}:temporal-host-info")
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME],
                status="active",
                timeout=1000,
                raise_on_blocked=False,
            )
            await run_sample_workflow(ops_test, use_env_variables=False)
