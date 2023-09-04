#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm scaling integration tests."""

import logging

import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME, run_sample_workflow, scale
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestScaling:
    """Integration tests for Temporal charm."""

    async def test_scaling_up(self, ops_test: OpsTest):
        """Scale Temporal worker charm up to 2 units."""
        await scale(ops_test, app=APP_NAME, units=2)

        await run_sample_workflow(ops_test)

    async def test_scaling_down(self, ops_test: OpsTest):
        """Scale Temporal charm down to 1 unit."""
        await scale(ops_test, app=APP_NAME, units=1)

        await run_sample_workflow(ops_test)
