#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm workload metrics relation integration tests."""

import logging

import pytest
from pytest_operator.plugin import OpsTest

from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
async def test_workload_metrics(ops_test: OpsTest):
    workload_metrics_port = 9090
    await ops_test.model.applications[APP_NAME].set_config({"workload-prometheus-port": str(workload_metrics_port)})

    await ops_test.model.deploy("cos-lite", trust=True, channel="latest/stable")
    logger.info("Deploying cos-lite bundle")
    await ops_test.model.wait_for_idle(
        apps=["traefik", "grafana", "loki", "prometheus", "catalogue", "alertmanager"],
        status="active",
        timeout=1000,
    )

    logger.info("Relating temporal-worker-k8s workload to prometheus")
    await ops_test.model.integrate(f"{APP_NAME}:workload-metrics-endpoint", "prometheus:metrics-endpoint")

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, "prometheus"],
        status="active",
        raise_on_blocked=False,
        timeout=600,
    )
