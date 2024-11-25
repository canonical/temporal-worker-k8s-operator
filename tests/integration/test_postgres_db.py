#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm postgresql relation integration tests."""

import logging

import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME, run_sample_workflow, scale
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    async def test_postgres_relation(self, ops_test: OpsTest):
        """Test Postgresql relation."""
        await scale(ops_test, app=APP_NAME, units=2)
        await ops_test.model.applications[APP_NAME].set_config({"db-name": "temporal-worker-k8s_db"})

        async with ops_test.fast_forward():
            logger.info("relating temporal-worker-k8s to postgresql-k8s charms")
            await ops_test.model.integrate(APP_NAME, "postgresql-k8s")

            await ops_test.model.wait_for_idle(
                apps=[APP_NAME, "postgresql-k8s"],
                status="active",
                raise_on_blocked=False,
                timeout=600,
            )

            await run_sample_workflow(ops_test, workflow_type="database")
