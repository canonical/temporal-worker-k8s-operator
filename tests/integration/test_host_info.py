#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm integration tests."""

import logging

import jubilant
import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    fast_forward,
    run_sample_workflow,
    wait_active,
    wait_blocked,
)

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestHostInfo:
    """Integration tests for Temporal charm."""

    def test_host_info_relation(self, juju: jubilant.Juju):
        """Relation values should take precedence over deprecated config fallback."""
        juju.config(APP_NAME, {"host": "deprecated-host:1"})
        juju.integrate(f"{APP_NAME_SERVER}:temporal-host-info", f"{APP_NAME}:temporal-host-info")
        with fast_forward(juju):
            # all_active alone can return before the invalid config and new
            # relation are processed; wait for the agents to settle as well.
            wait_active(juju, APP_NAME, timeout=1000)
            run_sample_workflow(juju, use_env_variables=False)

    def test_host_info_relation_removed_uses_fallback(self, juju: jubilant.Juju):
        """Remove host-info relation and verify deprecated host config fallback still works."""
        juju.config(APP_NAME, {"host": f"{APP_NAME_SERVER}:7233"})
        juju.remove_relation(
            f"{APP_NAME_SERVER}:temporal-host-info",
            f"{APP_NAME}:temporal-host-info",
        )
        with fast_forward(juju):
            wait_active(juju, APP_NAME, timeout=1000)
            run_sample_workflow(juju, use_env_variables=False)

    def test_host_info_relation_removed_blocks_until_restored(self, juju: jubilant.Juju):
        """Ensure worker blocks when relation is removed and no fallback host; recovers when restored."""
        juju.integrate(f"{APP_NAME_SERVER}:temporal-host-info", f"{APP_NAME}:temporal-host-info")
        juju.config(APP_NAME, {"host": ""})
        with fast_forward(juju):
            wait_active(juju, APP_NAME, timeout=1000)

        juju.remove_relation(
            f"{APP_NAME_SERVER}:temporal-host-info",
            f"{APP_NAME}:temporal-host-info",
        )
        with fast_forward(juju):
            wait_blocked(juju, APP_NAME, timeout=1000)

        juju.integrate(f"{APP_NAME_SERVER}:temporal-host-info", f"{APP_NAME}:temporal-host-info")
        with fast_forward(juju):
            wait_active(juju, APP_NAME, timeout=1000)
            run_sample_workflow(juju, use_env_variables=False)
