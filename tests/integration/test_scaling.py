#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm scaling integration tests."""

import logging

import jubilant
import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME, run_sample_workflow, scale

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestScaling:
    """Integration tests for Temporal charm."""

    def test_scaling_up(self, juju: jubilant.Juju):
        """Scale Temporal worker charm up to 2 units."""
        scale(juju, app=APP_NAME, units=2)

        run_sample_workflow(juju)

    def test_scaling_down(self, juju: jubilant.Juju):
        """Scale Temporal charm down to 1 unit."""
        scale(juju, app=APP_NAME, units=1)

        run_sample_workflow(juju)
