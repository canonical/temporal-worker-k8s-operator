#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration tests."""

import logging

import pytest
from helpers import run_sample_workflow
from integration.conftest import deploy  # noqa: F401, pylint: disable=W0611
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


# Skipped until local resources are supported:
# https://pythonlibjuju.readthedocs.io/en/latest/api/juju.model.html?highlight=deploy#juju.model.Model.deploy
@pytest.mark.skip
@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    async def test_basic_client(self, ops_test: OpsTest):
        """Connects a client and runs a basic Temporal workflow."""
        await run_sample_workflow(ops_test)
