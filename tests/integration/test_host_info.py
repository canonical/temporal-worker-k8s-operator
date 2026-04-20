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
        """Relation values should take precedence over deprecated config fallback."""
        await ops_test.model.applications[APP_NAME].set_config({"host": "deprecated-host:1"})
        await ops_test.model.integrate(f"{APP_NAME_SERVER}:temporal-host-info", f"{APP_NAME}:temporal-host-info")
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME],
                status="active",
                timeout=1000,
                raise_on_blocked=False,
            )
            await run_sample_workflow(ops_test, use_env_variables=False)

    async def test_host_info_relation_removed_uses_fallback(self, ops_test: OpsTest):
        """Remove host-info relation and verify deprecated host config fallback still works."""
        await ops_test.model.applications[APP_NAME].set_config({"host": f"{APP_NAME_SERVER}:7233"})
        await ops_test.juju(
            "remove-relation",
            f"{APP_NAME_SERVER}:temporal-host-info",
            f"{APP_NAME}:temporal-host-info",
        )
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME],
                status="active",
                timeout=1000,
                raise_on_blocked=False,
            )
            await run_sample_workflow(ops_test, use_env_variables=False)

    async def test_host_info_relation_removed_blocks_until_restored(self, ops_test: OpsTest):
        """Ensure worker blocks when relation is removed and no fallback host; recovers when restored."""
        await ops_test.model.integrate(f"{APP_NAME_SERVER}:temporal-host-info", f"{APP_NAME}:temporal-host-info")
        await ops_test.model.applications[APP_NAME].set_config({"host": ""})
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME],
                status="active",
                timeout=1000,
                raise_on_blocked=False,
            )

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
