#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm postgresql relation integration tests."""

import logging

import jubilant
import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME, fast_forward, run_sample_workflow, scale

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    def test_postgres_relation(self, juju: jubilant.Juju):
        """Test Postgresql relation."""
        scale(juju, app=APP_NAME, units=2)
        juju.config(APP_NAME, {"db-name": "temporal-worker-k8s_db"})

        with fast_forward(juju):
            logger.info("relating temporal-worker-k8s to postgresql-k8s charms")
            juju.integrate(APP_NAME, "postgresql-k8s")

            juju.wait(
                lambda status: jubilant.all_active(status, APP_NAME, "postgresql-k8s"),
                timeout=600,
            )

            run_sample_workflow(juju, workflow_type="database")
