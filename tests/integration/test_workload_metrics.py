#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm workload metrics relation integration tests."""

import logging

import pytest
import requests
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME, get_unit_url, run_sample_workflow
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
async def test_workload_metrics(ops_test: OpsTest):
    workflow_metrics_port = 10080
    await ops_test.model.applications[APP_NAME].set_config({"workflow-prometheus-port": str(workflow_metrics_port)})

    await ops_test.model.deploy("prometheus-k8s", trust=True, channel="latest/stable")
    logger.info("Deploying prometheus-k8s")
    await ops_test.model.wait_for_idle(
        apps=["prometheus-k8s"],
        status="active",
        timeout=1000,
    )

    logger.info("Relating temporal-worker-k8s workload to prometheus")
    await ops_test.model.integrate(f"{APP_NAME}:metrics-endpoint", "prometheus-k8s:metrics-endpoint")

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, "prometheus-k8s"],
        status="active",
        raise_on_blocked=False,
        timeout=600,
    )

    await run_sample_workflow(ops_test, workflow_type="workload_metrics")
    await _verify_metrics(ops_test)


@retry(stop=stop_after_attempt(10), wait=wait_exponential(multiplier=1, min=4, max=10))
async def _verify_metrics(ops_test: OpsTest):
    """Verify that workflow metrics exist and are scraped."""
    prometheus_url = await get_unit_url(ops_test, "prometheus-k8s", 0, 9090, "http")
    with requests.Session() as http:
        query_url = f"{prometheus_url}/api/v1/query?query=workload_custom_count"
        resp = http.get(query_url)

    assert resp.status_code == 200

    # if configured correctly there should be at least one metric present.
    assert resp.text.count("workload_custom_count") > 0
