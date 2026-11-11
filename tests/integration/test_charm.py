#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration tests."""

import logging

import jubilant
import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import run_sample_workflow

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    def test_basic_client(self, juju: jubilant.Juju):
        """Connects a client and runs a basic Temporal workflow."""
        run_sample_workflow(juju, use_env_variables=False)
        run_sample_workflow(juju, use_env_variables=True)
